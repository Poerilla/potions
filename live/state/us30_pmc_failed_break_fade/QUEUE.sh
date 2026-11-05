#!/usr/bin/env bash
# Wait for US30 ST+PMC causal revival full matrix, then kick Phase-1 fade taxonomy.
set -euo pipefail
REPO="${REPO:-/home/tester/hsm/potions}"
HUB="$REPO/live/state/us30_pmc_failed_break_fade"
REVIVAL_PID="${1:-788082}"
LOG="$HUB/queue.log"
mkdir -p "$HUB"
exec >>"$LOG" 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] queue armed; waiting for revival pid=$REVIVAL_PID"

while kill -0 "$REVIVAL_PID" 2>/dev/null; do
  sleep 60
done
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] revival pid $REVIVAL_PID exited"

# Prefer hub EMAIL from revival if present
if [[ -f "$REPO/live/state/us30_st_pmc_causal_revival_abc/EMAIL.txt" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%MZ)] revival EMAIL.txt present"
  tail -20 "$REPO/live/state/us30_st_pmc_causal_revival_abc/EMAIL.txt" || true
fi

export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
cd "$REPO"

# Launch headless agent to implement + run Phase 1→2 per RESEARCH_PLAN.md
PROMPT_FILE="$HUB/AGENT_PROMPT.txt"
cat >"$PROMPT_FILE" <<'EOF'
Follow live/state/us30_pmc_failed_break_fade/RESEARCH_PLAN.md exactly.

Context: US30 ST+PMC causal revival A/B/C full matrix just finished at live/state/us30_st_pmc_causal_revival_abc/. Path B (PMC retest) and Path A are expected negative on full history; do not revive fair-3R. Attribution showed ~90% post-close retest — that motivates a *failed-break fade*, not fading the ST+PMC signal.

Implement and run:
1) Phase 1 event taxonomy (PMC sweeps, no P&L) → hub live/state/us30_pmc_failed_break_fade/
2) Phase 2 frozen base replay: naive fade / reclaim-only / v1 confirmed fade controls with frozen params in RESEARCH_PLAN.md
3) Email via --email / live.notify_email; log via live.run_ledger
4) Write SUMMARY.md + EMAIL.txt with promote/reject stance per interpretation gates

Constraints: PMC level only; scale-out only (no add); causal 5m failure+confirmation → next 1m fill; early-close exclude; OANDA-style costs. Do not mix other levels or indicators in v1.
EOF

echo "[$(date -u +%Y-%m-%dT%H:%MZ)] launching agent for PMC failed-break fade"
nohup agent -p --force --workspace "$REPO" "$(cat "$PROMPT_FILE")" \
  >"$HUB/agent_launch.log" 2>&1 &
echo $! >"$HUB/agent.pid"
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] agent pid=$(cat "$HUB/agent.pid")"

# Also notify that queue fired
python - <<'PY' || true
from pathlib import Path
from live.notify_email import send_email
hub = Path("live/state/us30_pmc_failed_break_fade")
body = (hub / "RESEARCH_PLAN.md").read_text()[:2500]
send_email(
    subject="potions: queued US30 PMC failed-break fade starting",
    body="Revival matrix finished. Starting failed-PMC-break fade Phase 1/2.\nHub: %s\n\n%s" % (hub, body),
)
PY
echo "[$(date -u +%Y-%m-%dT%H:%MZ)] queue done"
