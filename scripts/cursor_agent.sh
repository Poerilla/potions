#!/usr/bin/env bash
# Cursor agent wrapper that bypasses broken corp TLS verify (missing Thales root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_LINK="${AGENT_BIN_REAL:-$(command -v agent || true)}"
if [[ -z "${AGENT_LINK}" ]]; then
  echo "agent not found on PATH" >&2
  exit 127
fi
# Resolve to versioned cursor-agent launcher dir
if command -v realpath >/dev/null 2>&1; then
  AGENT_SCRIPT="$(realpath "$AGENT_LINK")"
else
  AGENT_SCRIPT="$(readlink -f "$AGENT_LINK" 2>/dev/null || readlink "$AGENT_LINK")"
fi
SCRIPT_DIR="$(dirname "$AGENT_SCRIPT")"
NODE_BIN="$SCRIPT_DIR/node"
INDEX_JS="$SCRIPT_DIR/index.js"
BYPASS="$ROOT/scripts/cursor_agent_tls_bypass.cjs"

export NODE_TLS_REJECT_UNAUTHORIZED=0
# Skip wrapper's --use-system-ca path (still fails without root)
export AGENT_CLI_CREDENTIAL_STORE="${AGENT_CLI_CREDENTIAL_STORE:-file}"

exec -a agent "$NODE_BIN" -r "$BYPASS" "$INDEX_JS" "$@"
