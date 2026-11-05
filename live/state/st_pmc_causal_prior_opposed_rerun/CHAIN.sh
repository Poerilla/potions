#!/usr/bin/env bash
# Completed-hour ST sl25 → prior-opposed resting_limit for NQ then YM.
# ES/MES skipped (missing 1m archives).
set -uo pipefail
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
HUB="/home/tester/hsm/potions/live/state/st_pmc_causal_prior_opposed_rerun"
ST_HUB="/home/tester/hsm/potions/live/state/hourly_st_pmc_sl25_completed_hour"
LOG="$HUB/chain.log"
STATUS="$HUB/STATUS.txt"
mkdir -p "$HUB" "$ST_HUB"
exec > >(tee -a "$LOG") 2>&1

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "[$(ts)] CHAIN START pid=$$"

fail_email() {
  local stage="$1" rc="$2"
  python - <<PY
from live.notify_email import send_email
send_email(
  subject="potions: ST→prior-opposed causal rerun FAILED ($stage)",
  body=open("$HUB/STATUS.txt").read() + "\n\nSee $HUB/chain.log\nrc=$rc\n",
)
PY
}

run_st_sl25() {
  local market="$1"
  echo "RUNNING st_sl25 $market $(ts)" > "$STATUS"
  echo "[$(ts)] ST sl25_tp75_3r completed-hour $market"
  python - <<PY
from pathlib import Path
from live.broker import DEFAULT_TICK_SIZE
from live.hourly_st_pmc_loss_research import variants
from live.hourly_st_pmc_strategyplugin_variants import MARKET_CONFIGS, TICK_SIZE, run_variant
from live.ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, resample_hourly
from live.models import Bar
from live.run_ledger import begin_run, complete_run, fail_run

market = "$market"
cfg = MARKET_CONFIGS[market]
instrument = str(cfg["instrument"])
dbn = Path(cfg["dbn"])
daily = Path(cfg["daily"])
out = Path("$ST_HUB") / market
out.mkdir(parents=True, exist_ok=True)
variant = next(v for v in variants() if v.name == "sl25_tp75_3r")
tick = float(TICK_SIZE[instrument])
DEFAULT_TICK_SIZE[instrument] = tick
TICK_SIZE[instrument] = tick

rid = begin_run(
    run_class="broker_like",
    variant_slug="%s_hourly_st_pmc_sl25_tp75_3r_completed_hour" % market,
    instrument=instrument,
    hub_path=str(out),
    meta={"purpose": "prior_opposed_gate_tape", "causality": "completed_hour"},
)
try:
    print("Loading %s 1m → hourly…" % instrument, flush=True)
    gby = load_1m_by_ny_date_any(dbn.resolve(), market)
    one_m = concat_all_1m(gby)
    hourly = resample_hourly(one_m)
    bars = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=instrument,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(dbn),
            )
        )
    print("  %s hourly=%d 1m=%d" % (instrument, len(bars), len(one_m)), flush=True)
    result = run_variant(
        cfg=variant,
        bars=bars,
        output_root=out,
        dbn=dbn,
        daily_path=daily,
        instrument=instrument,
        market=market,
        force=True,
        quiet=True,
        one_m=one_m,
    )
    a = result.audit
    stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
    ns = (a.net_usd / abs(stress)) if stress else 0.0
    complete_run(
        rid,
        net_usd=a.net_usd,
        stress_dd_usd=stress,
        ns=ns,
        trades=a.trades,
        units=a.units,
        notes="completed-hour ST gate tape for prior-opposed",
    )
    summary = out / "SUMMARY.md"
    summary.write_text(
        "\n".join(
            [
                "# %s ST+PMC sl25_tp75_3r (completed-hour causal)" % instrument,
                "",
                "Gate tape for prior-opposed resting-limit. Signal bars shifted to hour-complete; fills on 1m.",
                "",
                "| Units | Net | Stress | N/S |",
                "|---:|---:|---:|---:|",
                "| %d | \$%.2f | \$%.2f | %.2f |" % (a.units, a.net_usd, stress, ns),
                "",
                "- State: \`states/%s/\`" % result.strategy_id,
                "- Driver: completed-hour via \`_replay_hourly_with_1m\`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Wrote %s N/S=%.2f" % (summary, ns), flush=True)
except Exception as exc:
    fail_run(rid, notes=str(exc))
    raise
PY
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "FAILED st_sl25 $market rc=$rc $(ts)" > "$STATUS"
    fail_email "st_sl25_$market" "$rc"
    exit "$rc"
  fi
}

run_prior_opposed() {
  local market="$1"
  local st_state="$ST_HUB/$market/states/${market}_hourly_st_pmc_sl25_tp75_3r"
  local out="/home/tester/hsm/potions/live/state/${market}_v2b_prior_opposed_stpmc_resting_limit"
  echo "RUNNING prior_opposed $market $(ts)" > "$STATUS"
  echo "[$(ts)] prior-opposed resting_limit $market (st_signal_stamp=completed_hour)"
  python -m live.nq_v2b_prior_opposed_replay \
    --market "$market" \
    --gate-mode resting_limit \
    --st-signal-stamp completed_hour \
    --st-fills "$st_state/fills.csv" \
    --st-orders "$st_state/orders.csv" \
    --output-root "$out" \
    --email
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "FAILED prior_opposed $market rc=$rc $(ts)" > "$STATUS"
    fail_email "prior_opposed_$market" "$rc"
    exit "$rc"
  fi
  python - <<PY
from pathlib import Path
from live.run_ledger import log_from_hub
hub = Path("$out")
try:
    log_from_hub(hub, run_class="broker_like", instrument="$market".upper())
except Exception as exc:
    print("ledger warn:", exc, flush=True)
PY
}

# NQ first (futures ST chain may still be on YM)
run_st_sl25 nq
run_prior_opposed nq

# YM after NQ (avoid double YM DBN load vs futures chain when possible)
run_st_sl25 ym
run_prior_opposed ym

# Refresh cross-market index snippet
python - <<'PY'
from pathlib import Path
import csv
hub = Path("/home/tester/hsm/potions/live/state/st_pmc_causal_prior_opposed_rerun")
rows = []
for m in ("nq", "ym"):
    p = Path(f"/home/tester/hsm/potions/live/state/{m}_v2b_prior_opposed_stpmc_resting_limit/summary.csv")
    if not p.exists():
        continue
    with p.open() as f:
        r = next(csv.DictReader(f))
    rows.append((m, r))
lines = [
    "# Prior-opposed resting_limit after completed-hour ST (2026-08-23)",
    "",
    "| Market | Trades | Net | Stress | N/S | Hub |",
    "|---|---:|---:|---:|---:|---|",
]
for m, r in rows:
    net = r.get("net_usd") or ""
    stress = r.get("intrabar_stress_dd_usd") or r.get("stress_dd_usd") or ""
    ns = r.get("net_over_stress") or r.get("net_stress") or ""
    trades = r.get("trades") or ""
    lines.append(
        f"| {m.upper()} | {trades} | {net} | {stress} | {ns} | `live/state/{m}_v2b_prior_opposed_stpmc_resting_limit/` |"
    )
lines += [
    "",
    "ES/MES: skipped (missing 1m archives).",
    "See IMPACT.md.",
    "",
]
(hub / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
email = hub / "EMAIL.txt"
email.write_text(
    "\n".join(
        [
            "ST+PMC completed-hour → prior-opposed resting_limit rerun COMPLETE",
            "",
            *lines,
            f"Impact notes: {hub}/IMPACT.md",
            f"ST tapes: live/state/hourly_st_pmc_sl25_completed_hour/",
            "",
            "Live/demo: ST demos already hour-complete on emit; US30 London prior-opposed research seed fixed to avoid double +1h.",
            "ES/MES blocked (no 1m).",
            "",
        ]
    ),
    encoding="utf-8",
)
from live.notify_email import send_email
send_email(subject="potions: ST→prior-opposed causal rerun COMPLETE", body=email.read_text())
print("Emailed rollup", flush=True)
PY

echo "COMPLETE $(ts)" > "$STATUS"
echo "[$(ts)] CHAIN COMPLETE"
