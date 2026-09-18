#!/usr/bin/env bash
# Only remove old, unused tags from the two explicitly named project repositories.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 BACKEND_REPOSITORY FRONTEND_REPOSITORY DEPLOY_COMPLETED_AT" >&2
  exit 2
fi
backend_repository="$1"
frontend_repository="$2"
completed_at="$3"
if [[ ! "$completed_at" =~ ^[0-9]+$ ]] || [ "$completed_at" -lt 108000 ]; then
  echo "Invalid deployment timestamp; refusing cleanup." >&2
  exit 2
fi
cutoff=$((completed_at - 30 * 60 * 60))
for repository in "$backend_repository" "$frontend_repository"; do
  if [[ ! "$repository" =~ ^[a-zA-Z0-9._:/-]+$ ]]; then
    echo "Invalid repository; refusing cleanup." >&2
    exit 2
  fi
done

for repository in "$backend_repository" "$frontend_repository"; do
  candidates=$(docker image ls --filter "reference=$repository:*" --format '{{.Repository}} {{.Tag}}')
  while read -r actual_repository tag; do
    # Docker reference filters can match patterns: recheck the exact repository.
    [ "$actual_repository" = "$repository" ] || continue
    [ -n "$tag" ] && [ "$tag" != "<none>" ] || continue
    reference="$actual_repository:$tag"
    image_id=$(docker image inspect --format '{{.Id}}' "$reference")
    created=$(docker image inspect --format '{{.Created}}' "$reference")
    created_at=$(date -d "$created" +%s)
    if [ "$created_at" -ge "$cutoff" ]; then
      echo "Keep recent image: $reference"
      continue
    fi
    # Include stopped containers, and conservatively protect descendant images.
    containers=$(docker ps --all --quiet --filter "ancestor=$image_id")
    if [ -n "$containers" ]; then
      echo "Keep container-referenced image: $reference"
      continue
    fi
    echo "Remove unused image older than 30h: $reference"
    # Never force deletion; never remove other tags, volumes, or parent images.
    if ! docker image rm --no-prune "$reference"; then
      echo "Warning: could not remove $reference; keeping it." >&2
    fi
  done <<< "$candidates"
done
