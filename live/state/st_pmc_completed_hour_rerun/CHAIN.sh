#!/usr/bin/env bash
# Completed-hour causal ST+PMC rerun: futures → metals → FX → index CFD
set -uo pipefail
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
HUB_META="/home/tester/hsm/potions/live/state/st_pmc_completed_hour_rerun"
LOG="$HUB_META/chain.log"
STATUS="$HUB_META/STATUS.txt"
mkdir -p "$HUB_META"
exec > >(tee -a "$LOG") 2>&1

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "[$(ts)] CHAIN START pid=$$"
echo "RUNNING futures $(ts)" > "$STATUS"

fail_email() {
  local stage="$1" rc="$2"
  python - <<PY
from live.notify_email import send_email
send_email(
  subject="potions: ST+PMC completed-hour rerun FAILED ($stage)",
  body=("Stage: %s\nexit=%s\nlog: live/state/st_pmc_completed_hour_rerun/chain.log\n"
        % ("$stage", "$rc")),
)
PY
}

ledger_hub() {
  local hub="$1" inst="$2" slug="$3"
  python -m live.run_ledger log-hub --hub "$hub" --instrument "$inst" --run-class broker_like --variant-slug "$slug" || true
}

# --- Futures first ---
echo "[$(ts)] FUTURES force rerun ym mym nq mnq"
if ! python -m live.futures_st_pmc_runner_variants --force --email --markets ym mym nq mnq; then
  rc=$?
  echo "FAILED futures rc=$rc $(ts)" > "$STATUS"
  fail_email "futures" "$rc"
  exit "$rc"
fi
ledger_hub live/state/futures_st_pmc_runner_variants NQ futures_st_pmc_runner_variants_completed_hour
echo "DONE futures; RUNNING metals_fx $(ts)" > "$STATUS"

# --- Metals → FX → index CFD ---
echo "[$(ts)] FX/METALS/INDEX force rerun xauusd xagusd eurusd gbpusd usdjpy audjpy nas100"
if ! python -m live.fx_index_metals_st_pmc_runner_variants --force --email \
    --markets xauusd xagusd eurusd gbpusd usdjpy audjpy nas100; then
  rc=$?
  echo "FAILED metals_fx rc=$rc $(ts)" > "$STATUS"
  fail_email "metals_fx" "$rc"
  exit "$rc"
fi
ledger_hub live/state/fx_index_metals_st_pmc_runner_variants EURUSD fx_index_metals_st_pmc_runner_variants_completed_hour

echo "COMPLETE $(ts)" > "$STATUS"
echo "[$(ts)] CHAIN COMPLETE"
# Final rollup email (drivers already emailed per hub; this is the chain summary)
python - <<'PY'
from pathlib import Path
from live.notify_email import send_email

root = Path("/home/tester/hsm/potions/live/state")
parts = []
for hub in ("futures_st_pmc_runner_variants", "fx_index_metals_st_pmc_runner_variants"):
    summary = root / hub / "SUMMARY.md"
    parts.append("## %s\n%s\n" % (hub, summary.read_text(encoding="utf-8")[:4000] if summary.exists() else "(missing SUMMARY.md)"))
body = (
    "Completed-hour causal ST+PMC force-rerun finished.\n"
    "Order: futures (ym/mym/nq/mnq) → metals (xau/xag) → FX → NAS100.\n"
    "US30 already audited separately under us30_st_pmc_runner_variants.\n"
    "ES/MES skipped (1m archives missing).\n\n" + "\n".join(parts)
)
(root / "st_pmc_completed_hour_rerun" / "EMAIL_CHAIN.txt").write_text(body, encoding="utf-8")
send_email(subject="potions: ST+PMC completed-hour cross-market rerun COMPLETE", body=body)
print("sent chain completion email")
PY
