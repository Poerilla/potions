#!/usr/bin/env bash
# Remove files over GitHub's size limits from entire git history.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PATH="$HOME/.local/bin:$PATH"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  python3 -m pip install --user git-filter-repo
  export PATH="$HOME/.local/bin:$PATH"
fi

PATHS_FILE="$REPO_ROOT/scripts/large_files_to_strip.txt"
if [[ ! -f "$PATHS_FILE" ]]; then
  echo "Missing $PATHS_FILE"
  exit 1
fi

echo "Stripping $(wc -l < "$PATHS_FILE") large file path(s) from history..."
git filter-repo --force --invert-paths --paths-from-file "$PATHS_FILE"

echo "History rewritten. Largest remaining blobs:"
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '/^blob/ {if ($3 > 50000000) print $3/1024/1024 " MB", $4}' \
  | sort -rn \
  | head -10
