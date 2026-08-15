#!/usr/bin/env bash
# Headless Cursor CLI completion report for a potions strategy hub.
#
# Usage:
#   scripts/run_completion_report_agent.sh [hub_path] [--email-only|--agent|--both]
#
# Default hub: live/state/fx_index_metals_st_pmc_runner_variants
# Requires: CURSOR_API_KEY (for agent -p) and/or .env.resend (for email)
#
# Architecture:
#   1) Deterministic Python writes RUN_COMPLETE.json + COMPLETION_EMAIL.txt
#   2) Optional: agent -p --force applies strategy-completion-report skill
#   3) Deterministic Resend email of the short body

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-}/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
load_env_file() {
  # Safe KEY=VAL loader (handles spaces; does not execute values).
  local f="$1"
  [[ -f "$f" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "$line" || "$line" != *=* ]] && continue
    local key="${line%%=*}"
    local val="${line#*=}"
    key="$(echo "$key" | sed -e 's/[[:space:]]*$//')"
    val="$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    export "$key=$val"
  done <"$f"
}

load_env_file "$ROOT/.env.cursor"
load_env_file "$ROOT/.env.resend"
load_env_file "$ROOT/.env.notify"

HUB="${1:-live/state/fx_index_metals_st_pmc_runner_variants}"
MODE="${2:---both}"
LOG_DIR="$ROOT/live/state/job_notify"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/completion_report_${STAMP}.log"

exec > >(tee -a "$LOG") 2>&1
echo "== completion report $STAMP hub=$HUB mode=$MODE =="

python -m live.run_complete_status --hub "$HUB" --write --email-body
SUBJECT="$(python -c "from live.refresh_hub_snapshot import email_subject_for_hub; print(email_subject_for_hub('$HUB'))")"

case "$MODE" in
  --email-only)
    python -m live.notify_email \
      --subject "$SUBJECT" \
      --body-file "$HUB/COMPLETION_EMAIL.txt"
    echo "email-only done subject=$SUBJECT"
    exit 0
    ;;
esac

AGENT_BIN=""
if command -v agent >/dev/null 2>&1; then
  AGENT_BIN="$(command -v agent)"
elif [[ -x "$HOME/.local/bin/agent" ]]; then
  AGENT_BIN="$HOME/.local/bin/agent"
fi

if [[ -z "$AGENT_BIN" ]]; then
  echo "WARN: Cursor CLI 'agent' not found. Install: curl https://cursor.com/install -fsS | bash"
  echo "Falling back to deterministic email only."
  python -m live.notify_email \
    --subject "$SUBJECT" \
    --body-file "$HUB/COMPLETION_EMAIL.txt" || true
  exit 0
fi

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "WARN: CURSOR_API_KEY unset — put it in .env.cursor"
fi

# This host MITMs TLS (Zscaler/Thales). Node cannot verify the incomplete
# corporate chain; curl can. Disable verify for agent CLI only.
export NODE_TLS_REJECT_UNAUTHORIZED="${NODE_TLS_REJECT_UNAUTHORIZED:-0}"

PROMPT="Use the strategy-completion-report skill.
Process hub: $HUB
Read RUN_COMPLETE.json, summary.csv, SUMMARY.md, and related audits.
Write COMPLETION_REPORT.md and refresh COMPLETION_EMAIL.txt using templates under
.cursor/skills/strategy-completion-report/templates/.
Update STATUS.json classifications with evidence.
Do not promote without complete accounting/currency normalization.
Do not commit or push unless explicitly requested.
Then stop."

# Corp TLS: agent’s internal stack needs Thales Devices CA V4 root installed
# (L2 alone → UNABLE_TO_GET_ISSUER_CERT). Email path still works via curl/Resend.

echo "Running: $AGENT_BIN -p --force --trust …"
set +e
agent_out="$("$AGENT_BIN" -p --force --trust --output-format text "$PROMPT" 2>&1)"
rc=$?
set -e
printf '%s\n' "$agent_out"
echo "agent exit=$rc"
if [[ "$rc" -ne 0 ]] || [[ "$agent_out" == *"unable to get issuer certificate"* ]] || [[ "$agent_out" == *"Failed to reach the Cursor API"* ]]; then
  echo "WARN: agent CLI failed (often missing Thales Devices CA V4 under Zscaler)."
  echo "      Deterministic email still sends. Install root CA or run agent off this host."
  rc=0  # do not fail the job notify path
fi

# Always send deterministic (or agent-refreshed) email body.
# Recompute subject after agent may have refreshed the snapshot.
SUBJECT="$(python -c "from live.refresh_hub_snapshot import email_subject_for_hub; print(email_subject_for_hub('$HUB'))")"
if [[ -f "$HUB/COMPLETION_EMAIL.txt" ]]; then
  python -m live.notify_email \
    --subject "$SUBJECT" \
    --body-file "$HUB/COMPLETION_EMAIL.txt" || true
fi

echo "log=$LOG"
exit "$rc"
