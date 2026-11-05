#!/usr/bin/env bash
# Wait for US30 continuation slippage stress, then kick PMC fade × structure-bias overlay.
set -euo pipefail
REPO="${REPO:-/home/tester/hsm/potions}"
HUB="$REPO/live/state/us30_pmc_failed_break_fade_structure_bias"
STRESS_PID="${1:-824591}"
LOG="$HUB/queue.log"
mkdir -p "$HUB"
exec >>"$LOG" 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] queue armed; waiting for stress pid=$STRESS_PID"

while kill -0 "$STRESS_PID" 2>/dev/null; do
  sleep 60
done
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] stress pid $STRESS_PID exited"

STRESS_HUB="$REPO/live/state/us30_st_pmc_causal_revival_abc/continuation_audit/execution_stress"
if [[ -f "$STRESS_HUB/EMAIL.txt" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%MZ)] stress EMAIL.txt present"
  tail -20 "$STRESS_HUB/EMAIL.txt" || true
fi

export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
cd "$REPO"

PROMPT_FILE="$HUB/AGENT_PROMPT.txt"
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] launching agent for PMC fade structure-bias overlay"
nohup agent -p --force --workspace "$REPO" "$(cat "$PROMPT_FILE")" \
  >"$HUB/agent_launch.log" 2>&1 &
echo $! >"$HUB/agent.pid"
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] agent pid=$(cat "$HUB/agent.pid")"

python - <<'PY' || true
from pathlib import Path
from live.notify_email import send_email
hub = Path("live/state/us30_pmc_failed_break_fade_structure_bias")
body = (hub / "RESEARCH_PLAN.md").read_text()[:2800]
send_email(
    subject="potions: queued US30 PMC fade × structure-bias starting",
    body=(
        "Continuation slippage stress finished. Starting confirmed-fade × 4h "
        "StructureProgramEngine alignment study (Phase 1 descriptive + Phase 2 "
        "aligned/aligned+neut filters).\n"
        "Hub: %s\nDSR: TRL-2026-00189\nParent: us30_pmc_failed_break_fade "
        "(confirmed N=129 N/S 0.81).\n\n%s" % (hub, body)
    ),
)
PY
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] queue done"
