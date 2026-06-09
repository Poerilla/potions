#!/usr/bin/env bash
# Restore large files from the archive created by pack_large_files.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${ARCHIVE:-$REPO_ROOT/data/potions_large_files.tar.zst}"
MANIFEST="${MANIFEST:-${ARCHIVE%.tar.zst}.manifest}"
VERIFY=1

usage() {
  cat <<'EOF'
Usage: unpack_large_files.sh [options] [archive]

Extract large files back into the repo tree (paths preserved relative to repo root).

Options:
  -a, --archive PATH    Archive path (default: data/potions_large_files.tar.zst)
  -m, --manifest PATH   Manifest for checksum verification
  --no-verify           Skip sha256 verification
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--archive) ARCHIVE="$2"; MANIFEST="${ARCHIVE%.tar.zst}.manifest"; shift 2 ;;
    -m|--manifest) MANIFEST="$2"; shift 2 ;;
    --no-verify) VERIFY=0; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    *)
      ARCHIVE="$1"
      MANIFEST="${ARCHIVE%.tar.zst}.manifest"
      shift
      ;;
  esac
done

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Archive not found: $ARCHIVE" >&2
  echo "Download it from Drive/S3 into data/ first." >&2
  exit 1
fi

echo "Extracting $ARCHIVE -> $REPO_ROOT"
tar -C "$REPO_ROOT" --zstd -xf "$ARCHIVE"

if [[ "$VERIFY" -eq 1 ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    echo "Manifest not found: $MANIFEST (use --no-verify to skip)" >&2
    exit 1
  fi

  echo "Verifying checksums from $MANIFEST"
  failed=0
  while read -r sha size rel; do
    [[ -z "${rel:-}" || "$rel" == \#* ]] && continue
    target="$REPO_ROOT/$rel"
    if [[ ! -f "$target" ]]; then
      echo "  missing after extract: $rel" >&2
      failed=1
      continue
    fi
    actual="$(sha256sum "$target" | awk '{print $1}')"
    if [[ "$actual" != "$sha" ]]; then
      echo "  checksum mismatch: $rel" >&2
      failed=1
    fi
  done < "$MANIFEST"

  if [[ "$failed" -ne 0 ]]; then
    echo "Verification failed." >&2
    exit 1
  fi
  echo "All files verified."
fi

echo "Done. Large files restored under $REPO_ROOT"
