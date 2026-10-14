#!/usr/bin/env bash
# Install once as /usr/local/sbin/career-memory-deploy (root:root, mode 0755).
# Called by the restricted SSM document; EC2 instance role supplies AWS credentials.
set -Eeuo pipefail
umask 077
release_id=${1:?Expected release ID}
api_digest=${2:?Expected API digest}
web_digest=${3:?Expected web digest}
[[ "$release_id" =~ ^[0-9a-f]{40}-[0-9]+-[0-9]+$ ]] || exit 2
[[ "$api_digest" =~ ^sha256:[0-9a-f]{64}$ && "$web_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
root=${CAREER_MEMORY_ROOT:-/opt/career-memory}
config=${CAREER_MEMORY_DEPLOY_CONFIG:-/etc/career-memory-deploy.conf}
# This config is owned by root and contains only registry settings, never app secrets.
source "$config"
[[ "$AWS_REGION" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]] || exit 2
[[ "$ECR_REGISTRY" =~ ^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com$ ]] || exit 2
[[ "$API_REPOSITORY" =~ ^[a-z0-9][a-z0-9/_-]+$ && "$WEB_REPOSITORY" =~ ^[a-z0-9][a-z0-9/_-]+$ ]] || exit 2
test -f "$root/.env.deploy"
mkdir -p "$root/releases"
exec 9>"$root/deploy.lock"
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
export CAREER_MEMORY_LOCK_HELD=1
export AWS_DEFAULT_REGION="$AWS_REGION" AWS_PAGER=''
# Temporary registry credentials, removed on exit.
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
container=''
stage=''
cleanup() {
    [[ -z "$container" ]] || docker rm "$container" >/dev/null || true
    [[ -z "$stage" ]] || rm -rf -- "$stage"
    rm -rf -- "$DOCKER_CONFIG"
}
trap cleanup EXIT
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"
api_image="$ECR_REGISTRY/$API_REPOSITORY@$api_digest"
web_image="$ECR_REGISTRY/$WEB_REPOSITORY@$web_digest"
docker pull "$api_image"
docker pull "$web_image"
target="$root/releases/$release_id"
expected=$(printf 'API_IMAGE=%s\nWEB_IMAGE=%s' "$api_image" "$web_image")
if [[ -d "$target" ]]; then
    [[ "$(cat "$target/images.env")" == "$expected" ]] || { echo 'Release ID already has different images' >&2; exit 1; }
else
    stage=$(mktemp -d "$root/releases/.staging.XXXXXX")
    container=$(docker create "$api_image")
    docker cp "$container:/opt/career-memory-release/." "$stage/"
    docker rm "$container" >/dev/null
    container=''
    printf '%s\n' "$expected" > "$stage/images.env"
    mv "$stage" "$target"
    stage=''
fi
bash "$target/deploy/activate-release.sh" "$target"
