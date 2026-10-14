#!/usr/bin/env bash
set -euo pipefail
umask 077
tag=${1:?Expected a full commit SHA}
[[ "$tag" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid release tag' >&2; exit 1; }
root=/opt/career-memory
exec 9>"$root/deploy.lock"
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
test -f "$root/.env.deploy"
mkdir -p "$root/releases/$tag" "$root/backups"
tar -xzf "$root/incoming/$tag.tar.gz" -C "$root/releases/$tag"
cd "$root/releases/$tag"
export IMAGE_TAG="$tag" DEPLOY_ENV_FILE="$root/.env.deploy"
compose=(docker compose --env-file "$root/.env.deploy" -f compose.yaml -f compose.production.yaml)
"${compose[@]}" config --quiet
gzip -dc images.tar.gz | docker load
previous=$(readlink -f "$root/current" || true)
# Back up all persistent application state with writers stopped (SQLite + Chroma + blobs).
if docker volume inspect career-memory-data >/dev/null 2>&1; then
    "${compose[@]}" stop api worker
    if ! docker run --rm --user 0 --entrypoint tar -v career-memory-data:/state:ro \
        "career-memory-api:$tag" -C /state -czf - . > "$root/backups/$(date -u +%Y%m%dT%H%M%SZ)-$tag.tar.gz"; then
        "${compose[@]}" start api worker
        echo 'Backup failed; existing service restarted' >&2
        exit 1
    fi
fi
if ! "${compose[@]}" up -d --no-build --wait --wait-timeout 240; then
    echo 'Release failed health checks' >&2
    if [[ -n "$previous" && -d "$previous" && "$previous" != "$PWD" ]]; then
        export IMAGE_TAG="$(basename "$previous")"
        docker compose --env-file "$root/.env.deploy" -f "$previous/compose.yaml" \
            -f "$previous/compose.production.yaml" up -d --no-build --wait --wait-timeout 240
        echo 'Previous containers restored. Database schema is NOT reverted; inspect migrations and backup.' >&2
    fi
    exit 1
fi
ln -sfn "$root/releases/$tag" "$root/current"
echo "Activated release $tag"
