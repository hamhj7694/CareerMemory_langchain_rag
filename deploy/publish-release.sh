#!/usr/bin/env bash
set -euo pipefail
[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}-[0-9]+-[0-9]+$ ]] || exit 2
account=$(aws sts get-caller-identity --query Account --output text)
[[ "$account" =~ ^[0-9]{12}$ ]] || exit 2
registry="$account.dkr.ecr.$AWS_REGION.amazonaws.com"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$registry"
trap 'docker logout "$registry" >/dev/null' EXIT
gzip -dc images.tar.gz | docker load
docker tag "career-memory-api:$GITHUB_SHA" "$registry/$API_REPOSITORY:$RELEASE_ID"
docker tag "career-memory-web:$GITHUB_SHA" "$registry/$WEB_REPOSITORY:$RELEASE_ID"
docker push "$registry/$API_REPOSITORY:$RELEASE_ID"
docker push "$registry/$WEB_REPOSITORY:$RELEASE_ID"
api_digest=$(aws ecr describe-images --repository-name "$API_REPOSITORY" --image-ids "imageTag=$RELEASE_ID" --query 'imageDetails[0].imageDigest' --output text)
web_digest=$(aws ecr describe-images --repository-name "$WEB_REPOSITORY" --image-ids "imageTag=$RELEASE_ID" --query 'imageDetails[0].imageDigest' --output text)
[[ "$api_digest" =~ ^sha256:[0-9a-f]{64}$ && "$web_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || exit 2
printf 'API_DIGEST=%s\nWEB_DIGEST=%s\n' "$api_digest" "$web_digest" >> "$GITHUB_ENV"
printf 'Release `%s`\n\nAPI: `%s`\n\nWeb: `%s`\n' "$RELEASE_ID" "$api_digest" "$web_digest" >> "$GITHUB_STEP_SUMMARY"
