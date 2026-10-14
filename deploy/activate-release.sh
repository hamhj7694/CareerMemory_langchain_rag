#!/usr/bin/env bash
# Called by the host bootstrap while holding deploy.lock. Never sources .env.deploy.
set -Eeuo pipefail
umask 077
root=${CAREER_MEMORY_ROOT:-/opt/career-memory}
release=${1:?Expected release directory}
[[ ${CAREER_MEMORY_LOCK_HELD:-} == 1 && "$release" == "$root/releases/"* ]] || exit 2
export DEPLOY_ENV_FILE="$root/.env.deploy"
unset API_IMAGE WEB_IMAGE IMAGE_TAG
compose_at() {
    local directory=$1; shift
    docker compose --project-name career-memory --env-file "$DEPLOY_ENV_FILE" \
        --env-file "$directory/images.env" -f "$directory/compose.yaml" \
        -f "$directory/compose.production.yaml" "$@"
}
previous=$(readlink -f "$root/current" || true)
rollback_needed=0
finish() {
    local result=$?
    trap - EXIT INT TERM
    if (( result != 0 && rollback_needed == 1 )); then
        if [[ -n "$previous" && -d "$previous" ]]; then
            echo 'Deployment failed; restoring previous release' >&2
            if compose_at "$previous" up -d --no-build --wait --wait-timeout 300; then
                echo 'Previous containers restored; database was not rewound.' >&2
            else
                echo 'ROLLBACK FAILED: inspect SSM logs and restore service manually.' >&2
            fi
        else
            compose_at "$release" stop || true
            echo 'First deployment failed; no previous release exists.' >&2
        fi
    fi
    exit "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
compose_at "$release" config --quiet
compose_at "$release" pull
mkdir -p "$root/backups"
rollback_needed=1
if docker volume inspect career-memory-data >/dev/null 2>&1; then
    if [[ -n "$previous" && -d "$previous" ]]; then
        compose_at "$previous" stop api worker
    else
        compose_at "$release" stop api worker
    fi
    # Stop writers for a consistent SQLite / Chroma / upload backup.
    api_image=$(sed -n 's/^API_IMAGE=//p' "$release/images.env")
    backup="$root/backups/$(date -u +%Y%m%dT%H%M%SZ)-$(basename "$release").tar.gz"
    docker run --rm --user 0 --entrypoint tar -v career-memory-data:/state:ro \
        "$api_image" -C /state -czf - . > "$backup.partial"
    mv "$backup.partial" "$backup"
fi
compose_at "$release" up -d --no-build --wait --wait-timeout 300
# Exercise public DNS, TLS and both proxies. No AI calls or credentials in logs.
compose_at "$release" exec -T api python -c '
import os, time, urllib.request
url = os.environ["FRONTEND_URL"].rstrip("/") + "/health"
assert url.startswith("https://"), "Production FRONTEND_URL must use HTTPS"
for attempt in range(12):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.status == 200
        break
    except Exception:
        if attempt == 11: raise
        time.sleep(5)
'
# Atomic link replacement; only a healthy release becomes current.
if [[ -n "$previous" && "$previous" != "$release" ]]; then
    ln -sfn "$previous" "$root/previous.next"
    mv -Tf "$root/previous.next" "$root/previous"
fi
ln -sfn "$release" "$root/current.next"
mv -Tf "$root/current.next" "$root/current"
rollback_needed=0
echo "Activated release $(basename "$release")"
