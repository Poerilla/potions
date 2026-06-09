#!/usr/bin/env bash
# Bundle repo-local large files (listed in large_files_to_strip.txt) into one archive.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATHS_FILE="$REPO_ROOT/scripts/large_files_to_strip.txt"
OUTPUT="${OUTPUT:-$REPO_ROOT/data/potions_large_files.tar.zst}"
MANIFEST="${MANIFEST:-${OUTPUT%.tar.zst}.manifest}"
STRICT=0

usage() {
  cat <<'EOF'
Usage: pack_large_files.sh [options]

Create a single compressed archive of large files excluded from GitHub.
Upload the archive to Google Drive, S3, etc., then restore with unpack_large_files.sh.

Options:
  -o, --output PATH     Archive path (default: data/potions_large_files.tar.zst)
  -m, --manifest PATH   Manifest path (default: alongside archive)
  --strict              Fail if any listed file is missing
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUTPUT="$2"; MANIFEST="${OUTPUT%.tar.zst}.manifest"; shift 2 ;;
    -m|--manifest) MANIFEST="$2"; shift 2 ;;
    --strict) STRICT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ ! -f "$PATHS_FILE" ]]; then
  echo "Missing paths file: $PATHS_FILE" >&2
  exit 1
fi

mapfile -t paths < <(grep -v '^[[:space:]]*$' "$PATHS_FILE")

present=()
missing=()
for rel in "${paths[@]}"; do
  if [[ -f "$REPO_ROOT/$rel" ]]; then
    present+=("$rel")
  else
    missing+=("$rel")
  fi
done

if [[ "${#present[@]}" -eq 0 ]]; then
  echo "No listed files found under $REPO_ROOT" >&2
  echo "Expected paths from $PATHS_FILE" >&2
  exit 1
fi

if [[ "${#missing[@]}" -gt 0 ]]; then
  echo "Missing ${#missing[@]} file(s):" >&2
  printf '  %s\n' "${missing[@]}" >&2
  if [[ "$STRICT" -eq 1 ]]; then
    exit 1
  fi
  echo "Packing ${#present[@]} present file(s) only." >&2
fi

mkdir -p "$(dirname "$OUTPUT")"
tmp_list="$(mktemp)"
trap 'rm -f "$tmp_list"' EXIT
printf '%s\n' "${present[@]}" > "$tmp_list"

echo "Creating $OUTPUT"
tar -C "$REPO_ROOT" --zstd -cf "$OUTPUT" -T "$tmp_list"

{
  echo "# potions large files manifest"
  echo "# created: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# archive: $(basename "$OUTPUT")"
  echo "# paths_file: scripts/large_files_to_strip.txt"
  echo "# format: sha256 bytes path"
  for rel in "${present[@]}"; do
    size="$(stat -c%s "$REPO_ROOT/$rel")"
    hash="$(sha256sum "$REPO_ROOT/$rel" | awk '{print $1}')"
    echo "$hash $size $rel"
  done
} > "$MANIFEST"

archive_bytes="$(stat -c%s "$OUTPUT")"
total_source=0
for rel in "${present[@]}"; do
  total_source=$((total_source + $(stat -c%s "$REPO_ROOT/$rel")))
done

echo "Packed ${#present[@]} file(s)"
echo "  source: $(numfmt --to=iec-i --suffix=B "$total_source" 2>/dev/null || echo "${total_source} bytes")"
echo "  archive: $(numfmt --to=iec-i --suffix=B "$archive_bytes" 2>/dev/null || echo "${archive_bytes} bytes")"
echo "  manifest: $MANIFEST"
echo ""
echo "Upload these two files to Drive/S3:"
echo "  $OUTPUT"
echo "  $MANIFEST"
