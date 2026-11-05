#!/usr/bin/env bash
# After US30 PMC fade × structure-bias finishes, notify that the NQ structure-
# change event study (Phase 1) is clear to start. Does NOT auto-launch a heavy
# 1m walk — agent/operator starts Phase 1 explicitly once CPU is free.
set -euo pipefail
REPO="${REPO:-/home/tester/hsm/potions}"
HUB="$REPO/live/state/nq_structure_change_event_study"
BIAS_HUB="$REPO/live/state/us30_pmc_failed_break_fade_structure_bias"
STRESS_PID="${1:-824591}"
LOG="$HUB/queue.log"
mkdir -p "$HUB"
exec >>"$LOG" 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] structure-change atlas queue armed"

# 1) Wait for continuation stress
while kill -0 "$STRESS_PID" 2>/dev/null; do
  sleep 60
done
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] stress pid $STRESS_PID exited"

# 2) Wait for structure-bias QUEUE.sh and any agent it spawned
BIAS_QUEUE_PID_FILE="$BIAS_HUB/queue.pid"
BIAS_AGENT_PID_FILE="$BIAS_HUB/agent.pid"
if [[ -f "$BIAS_QUEUE_PID_FILE" ]]; then
  BQ=$(cat "$BIAS_QUEUE_PID_FILE" || true)
  while [[ -n "${BQ:-}" ]] && kill -0 "$BQ" 2>/dev/null; do
    sleep 60
  done
  echo "[$(date -u +%Y-%m-%dT%H:%MZ)] bias QUEUE.sh exited"
fi
# Agent may start after queue; wait if present
sleep 30
if [[ -f "$BIAS_AGENT_PID_FILE" ]]; then
  BA=$(cat "$BIAS_AGENT_PID_FILE" || true)
  while [[ -n "${BA:-}" ]] && kill -0 "$BA" 2>/dev/null; do
    sleep 120
  done
  echo "[$(date -u +%Y-%m-%dT%H:%MZ)] bias agent exited (or never ran)"
fi
# Also wait until RUN_COMPLETE or SUMMARY exists as a soft done signal
for _ in $(seq 1 180); do
  if [[ -f "$BIAS_HUB/RUN_COMPLETE.json" || -f "$BIAS_HUB/SUMMARY.md" || -f "$BIAS_HUB/EMAIL.txt" ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%MZ)] bias hub artifact present"
    break
  fi
  # If no agent and queue gone, don't block forever
  if [[ ! -f "$BIAS_AGENT_PID_FILE" ]] || ! kill -0 "$(cat "$BIAS_AGENT_PID_FILE" 2>/dev/null)" 2>/dev/null; then
    if [[ ! -f "$BIAS_QUEUE_PID_FILE" ]] || ! kill -0 "$(cat "$BIAS_QUEUE_PID_FILE" 2>/dev/null)" 2>/dev/null; then
      echo "[$(date -u +%Y-%m-%dT%H:%MZ)] no bias workers; proceeding to notify"
      break
    fi
  fi
  sleep 60
done

export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
cd "$REPO"
cat >"$HUB/EMAIL_READY.txt" <<EOF
potions: NQ structure-change event study CPU CLEAR for Phase 1

Hub: $HUB
Phase 0 freeze already on disk:
  - STRUCTURE_CHANGE_RESEARCH_CONTRACT.yaml
  - EVENT_TAXONOMY.md

Upstream finished:
  - us30 continuation slippage stress
  - us30_pmc_failed_break_fade_structure_bias (queued overlay)

Next: start Phase 1 pure event study on NQ only (4h primary, 1h secondary),
matched controls, no strategy prototypes yet.

Cross-market roster (NAS100/US30/EURUSD/USDJPY/XAUUSD + MNQ/MYM; MES
data-blocked) stays PENDING until you approve the NQ atlas:
  live/state/structure_change_event_study_cross_market/APPROVAL_GATE.md
Do NOT auto-start CFDs/micros on this email.

Engine freeze: StructureProgramEngine left/right=2, list=20, takeouts=2.
Penetration diagnostic: 0.05 ATR (+ zero-buffer control).
EOF

python - <<'PY'
from pathlib import Path
from live.notify_email import send_email
hub = Path("live/state/nq_structure_change_event_study")
body = (hub / "EMAIL_READY.txt").read_text()
send_email(subject="potions: NQ structure-change atlas CPU CLEAR (Phase 1 ready)", body=body)
print("emailed Phase 1 ready")
PY
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] queue done — Phase 1 ready email sent"
