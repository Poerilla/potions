---
name: potions-oanda-tick-demo-plugin-parity
description: >-
  Replays stored OANDA practice stream ticks (fx_ticks / rth_ticks) through the
  live/demo aggregation path and a fresh Engine+StrategyPlugin on the same bars,
  then compares fills. Always emails and updates broker_run_ledger.csv. Use when
  checking OANDA demo↔plugin trade parity, wiring after a new practice sleeve,
  UTC/NY session-clock bugs, or tick-fed live vs plugin match (NAS100 clean-break,
  USDJPY Monday OR, Asia-range).
---

# Potions OANDA-tick demo ↔ StrategyPlugin parity

**Scope:** OANDA-gathered practice ticks only — **not** `fx/*.csv` research OHLC.

Compares:

1. **Demo path** — ticks → quote bar builders / aggregators used by the live demo → Engine+PaperBroker  
2. **Plugin path** — the **same** completed signal bars → fresh Engine+PaperBroker + same StrategyPlugin config  

**Pass:** sorted fill keys `(ts_minute, side, qty, reason)` MATCH (same-bar multi-fill order is ignored).

## Always do

1. Run with `--email` (writes hub `EMAIL.txt` + Resend).  
2. Log `broker_run_ledger.csv` via driver `begin_run` / `complete_run` (`run_class=audit`) — include `net_usd`, `trades`, `replay_start` / `replay_end`, `meta.verdict`.  
3. Do **not** wait for the user to ask for email or ledger.

## Environment

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export POTIONS_RUN_LEDGER="/home/tester/hsm/potions/data/validation/broker_run_ledger.csv"
set -a && source live/demo/.env && set +a   # only if also restarting daemons
```

## Drivers (current live UP books)

| Book | Account | Driver | Tick source | Hub |
|------|---------|--------|-------------|-----|
| NAS100 clean-break `trail06_m4_e2_out_be` | `-003` | `python -m live.nas100_clean_break_demo_plugin_tick_parity --email` | Prefer `nas100_v2b_ungated_oanda/.../rth_ticks` (fallback: clean-break demo `rth_ticks`) | `live/state/nas100_clean_break_demo_plugin_tick_parity_v1/` |
| USDJPY Monday OR + Asia-range | `-005` / `-004` | `python -m live.usdjpy_live_demo_plugin_tick_parity --email` | Each demo’s `.../state/events/fx_ticks` | `live/state/usdjpy_live_demo_plugin_tick_parity_v1/` |

Convenience wrapper (both families):

```bash
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/run_parity.py --email
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/run_parity.py --email --smoke
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/run_parity.py --email --book nas100
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/run_parity.py --email --book usdjpy
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/run_parity.py --email --book usdjpy --usdjpy-book monday
```

## Workflow

1. Confirm which live OANDA demos are in scope (usually the UP practice sleeves).  
2. Confirm tick dirs exist (`fx_ticks` / `rth_ticks` with `*.jsonl`).  
3. Run driver(s) with `--email` (full archive unless `--smoke` / `--max-days`).  
4. Read hub `SUMMARY.md` / `RUN_COMPLETE.json` / `demo_vs_plugin.json`.  
5. Verify ledger rows: `python -m live.run_ledger tail -n 20` — look for `*_demo_plugin_tick_parity`.  
6. If MATCH but zero fills, say so explicitly (wiring ok, weak economic sample).  
7. If MISMATCH: check UTC vs NY session clocks, aggregator labeling, Asia OR inject, and same-bar fill order before treating as a live bug.

## Ledger backfill (existing hubs)

When a hub already has `RUN_COMPLETE.json` but the ledger row is missing metrics / wrong verdict:

```bash
python3 .cursor/skills/potions-oanda-tick-demo-plugin-parity/scripts/backfill_ledger.py
```

Updates known run_ids for the 2026-08-31 / 2026-09-01 parity hubs (net, trades, replay window, corrected MATCH meta). Safe to re-run (idempotent enrich).

## Related

- `potions-oanda-live-sim-reconcile` — live **fills.csv** vs plugin on **stored demo bars** (not tick-fed)  
- `potions-run-ledger` — ledger API  
- `potions-job-email` — Resend completion mail  
- `potions-demo-status` — daemon heartbeats  
- `potions-oanda-reconcile` — broker position sync  
