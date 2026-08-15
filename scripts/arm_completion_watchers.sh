#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export PATH="$HOME/.local/bin:$PATH"
NOTIFY="$ROOT/live/state/job_notify"
mkdir -p "$NOTIFY"

# Stop prior python watchers only
ps -eo pid,cmd | awk '/[p]ython -u -m live.notify_when_done/{print $1}' | while read -r pid; do
  kill "$pid" 2>/dev/null || true
done
sleep 1

pid_for() {
  ps -eo pid,cmd | awk -v pat="$1" '$0 ~ pat {print $1; exit}'
}

EUR=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets eurusd')
GBP=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets gbpusd')
JPY=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets usdjpy')
AUD=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets audjpy --only')
XAU=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets xauusd --only')
XAG=$(pid_for 'python.*fx_index_metals_st_pmc_runner_variants --force --markets xagusd --only')
SWEEP=$(pid_for 'python.*st_pmc_runner_length_sweep --markets usdjpy')

echo "eur=$EUR gbp=$GBP jpy=$JPY aud=$AUD xau=$XAU xag=$XAG sweep=$SWEEP" | tee "$NOTIFY/arm.log"

P3=()
[[ -n "${AUD:-}" ]] && P3+=("$AUD")
[[ -n "${XAU:-}" ]] && P3+=("$XAU")
[[ -n "${XAG:-}" ]] && P3+=("$XAG")
if [[ ${#P3[@]} -gt 0 ]]; then
  nohup python -u -m live.notify_when_done --pids "${P3[@]}" --poll-sec 120 \
    --subject "potions: AUDJPY/XAU/XAG fair 3R DONE" \
    --summary fx3r --markets audjpy xauusd xagusd \
    >"$NOTIFY/watch_3r.log" 2>&1 &
  echo "watch_3r=$!" | tee -a "$NOTIFY/arm.log"
else
  python -m live.format_job_summary --kind fx3r --markets audjpy xauusd xagusd >"$NOTIFY/fx3r_body.txt"
  python -m live.notify_email --subject "potions: AUDJPY/XAU/XAG fair 3R (snapshot)" \
    --body-file "$NOTIFY/fx3r_body.txt" >>"$NOTIFY/arm.log" 2>&1 || true
fi

B1=()
[[ -n "${EUR:-}" ]] && B1+=("$EUR")
[[ -n "${GBP:-}" ]] && B1+=("$GBP")
[[ -n "${JPY:-}" ]] && B1+=("$JPY")
if [[ ${#B1[@]} -gt 0 ]]; then
  nohup python -u -m live.notify_when_done --pids "${B1[@]}" --poll-sec 180 \
    --subject "potions: EUR/GBP/USDJPY runners (incl indef) DONE" \
    --summary fx --markets eurusd gbpusd usdjpy \
    >"$NOTIFY/watch_batch1.log" 2>&1 &
  echo "watch_batch1=$!" | tee -a "$NOTIFY/arm.log"
else
  echo "batch1 workers gone" | tee -a "$NOTIFY/arm.log"
fi

if [[ -n "${SWEEP:-}" ]]; then
  nohup python -u -m live.notify_when_done --pids "$SWEEP" --poll-sec 180 \
    --subject "potions: runner length sweep FX DONE" \
    --summary sweep --markets usdjpy eurusd gbpusd us30 nas100 \
    >"$NOTIFY/watch_sweep.log" 2>&1 &
  echo "watch_sweep=$!" | tee -a "$NOTIFY/arm.log"
fi

nohup python -u -m live.notify_when_done \
  --pgrep 'live.fx_index_metals_st_pmc_runner_variants' \
  --poll-sec 300 \
  --subject "potions: ALL FX/index/metals ST+PMC jobs DONE" \
  --summary all \
  --on-complete 'scripts/run_completion_report_agent.sh live/state/fx_index_metals_st_pmc_runner_variants --both' \
  >"$NOTIFY/watch_all_fx.log" 2>&1 &
echo "watch_all_fx=$!" | tee -a "$NOTIFY/arm.log"

sleep 1
ps -eo pid,cmd | awk '/[p]ython -u -m live.notify_when_done/{print}' | tee -a "$NOTIFY/arm.log"
echo "armed" | tee -a "$NOTIFY/arm.log"
