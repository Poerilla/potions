#!/usr/bin/env bash
# Push commits to origin/main in small batches to avoid huge HTTP pack uploads.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BATCH_SIZE="${1:-1}"
REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-main}"
MAX_RETRIES="${MAX_RETRIES:-3}"

git config http.postBuffer 524288000
git config http.version HTTP/1.1

remote_sha="$(git ls-remote "$REMOTE" "refs/heads/$BRANCH" | awk '{print $1}')"
if [[ -z "$remote_sha" ]]; then
  echo "Could not read $REMOTE/$BRANCH"
  exit 1
fi

mapfile -t commits < <(git rev-list --reverse "${remote_sha}..HEAD")
total="${#commits[@]}"

if [[ "$total" -eq 0 ]]; then
  echo "Already up to date with $REMOTE/$BRANCH ($remote_sha)"
  exit 0
fi

echo "Pushing $total commit(s) to $REMOTE/$BRANCH in batches of $BATCH_SIZE"
echo "Starting from remote: $remote_sha"

idx=0
while [[ "$idx" -lt "$total" ]]; do
  end=$((idx + BATCH_SIZE - 1))
  if [[ "$end" -ge "$total" ]]; then
    end=$((total - 1))
  fi
  target="${commits[$end]}"
  batch_num=$((end + 1))
  subject="$(git log -1 --format='%s' "$target")"

  attempt=1
  while true; do
    echo ""
    echo "[$batch_num/$total] pushing $target"
    echo "  $subject"
    if git push "$REMOTE" "${target}:refs/heads/${BRANCH}"; then
      break
    fi
    if [[ "$attempt" -ge "$MAX_RETRIES" ]]; then
      echo "Failed after $MAX_RETRIES attempts at commit $batch_num/$total"
      echo "Resume with: $0 $BATCH_SIZE"
      exit 1
    fi
    attempt=$((attempt + 1))
    sleep_secs=$((attempt * 5))
    echo "Retry $attempt/$MAX_RETRIES in ${sleep_secs}s..."
    sleep "$sleep_secs"
  done

  idx=$((end + 1))
done

echo ""
echo "Done. $REMOTE/$BRANCH is now at $(git rev-parse HEAD)"
