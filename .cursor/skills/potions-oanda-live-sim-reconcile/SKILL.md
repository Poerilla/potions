---
name: potions-oanda-live-sim-reconcile
description: >-
  Reconciles live/demo OANDA strategy fills against Engine+PaperBroker
  StrategyPlugin replays on the demo's stored bars. Detects entry mismatches
  and spawn-config drift (e.g. missing skip_entry_months). Use when checking
  whether an OANDA demo is behaving correctly, comparing live vs sim trades,
  auditing Monday OR / v2b / ST+PMC practice books, or after daemon restarts.
---

# Potions OANDA live ↔ sim reconcile

Hub: [`live/demo/README.md`](../../../live/demo/README.md)  
Scope: every `live/demo/*_oanda/` run that has `state/strategy_instances.csv` + bars.

## Environment

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
unset OPENSSL_CONF SSL_CERT_FILE SSL_CERT_DIR NODE_EXTRA_CA_CERTS NODE_OPTIONS AGENT_CLI_CREDENTIAL_STORE
```

## One-shot (all OANDA demos)

```bash
python3 .cursor/skills/potions-oanda-live-sim-reconcile/scripts/reconcile_oanda_demos.py
# single book:
python3 .cursor/skills/potions-oanda-live-sim-reconcile/scripts/reconcile_oanda_demos.py --demo usdjpy_monday_or_ungated_oanda
# also replay with fresh spawn payload (flags Aug/Sep skip drift etc.):
python3 .cursor/skills/potions-oanda-live-sim-reconcile/scripts/reconcile_oanda_demos.py --also-fresh
```

Writes under `live/state/_oanda_live_sim_reconcile/<demo>/` (gitignored-style scratch; safe to delete).

## What “pass” means

| Status | Meaning |
|--------|---------|
| `MATCH` | Exact `(ts_minute, side, qty)` entry sequence vs live |
| `FUZZY` | Every live entry has a sim twin within **±2 minutes**, same side/qty (common on v2b OANDA latency) |
| `DRIFT` / `FUZZY_DRIFT` | Tape ok under **live** config, but `config_json` missing/differing fresh spawn overlays |
| `MISMATCH` | Side/qty/time not reconcilable — investigate stream/broker |
| `SKIP` / `ERROR` | No bars / exception |

Also: sim **and** live entries before `RUN_META.started_at` are dropped from the score (seed history + pre-restart fills). Full tape stays on disk for PnL forensics.

**Restart gotcha:** spawn daemons with `set -a; source live/demo/.env; set +a` so `OANDA_TOKEN` is present (spawn does not auto-load `.env`).

## Workflow

1. Confirm daemon UP (`potions-demo-status`) and note open qty.
2. Run reconciler for the book(s) in question.
3. If **live-config** mismatches → bug in stream/aggregation/broker routing (investigate `PROGRESS.log` / `run.log`).
4. If **live-config** matches but **fresh** differs → daemon spawned on stale config; restart with current payload (stop → `--daemon`) so `bootstrap_store` upserts `strategy_instances`.
5. Do **not** wipe `fills.csv` on restart unless the user asks; history stays; new rules apply going forward.

## Current OANDA books (inventory)

| Run dir | Plugin | Signal TF |
|---------|--------|-----------|
| `eurusd_v2b_ungated_oanda` | `v2b_scaleout` | 1m |
| `nas100_v2b_ungated_oanda` | `v2b_scaleout` | 1m |
| `spx500_v2b_ungated_oanda` | `v2b_scaleout` | 1m |
| `us30_v2b_ungated_oanda` | `v2b_scaleout` | 1m |
| `usdjpy_monday_or_ungated_oanda` | `monday_or_breakout` | 15m |
| `usdjpy_asia_range_london_oanda` | `v2b_scaleout` | 1m (Asia OR + London arm) |
| `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | `hourly_st_pmc_retest` | 1h+1m |
| `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | `hourly_st_pmc_retest` | 1h+1m |
| `us30_hourly_st_pmc_sl50_tp150_3r_oanda` | `hourly_st_pmc_retest` | 1h+1m |
| `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | `hourly_st_pmc_retest` | 1h+1m |
| `us30_london_prior_opposed_oanda` | `v2b_scaleout` (prior-opposed, ¼ size) | 1m + live ST gate |

## Report format

For each demo: `MATCH` / `MISMATCH` / `DRIFT` / `SKIP`, entry counts, first differing key, config keys missing vs fresh spawn.

## Interpreting non-Monday results

- **`monday_or_breakout`**: expect `MATCH` (exact) once config drift is fixed — gold-path check.
- **`v2b_scaleout`**: often `FUZZY` or residual `MISMATCH` from practice-stream gaps, OR arm vs fill latency, and partial first sessions. Treat as smoke test; dig in only when sides/qty clearly diverge for many sessions.
- **`hourly_st_pmc_retest`**: needs seed 1h history; compare only post-`started_at`. Open multi-lot entries can land as several `reason=entry` fills vs one sim bar — investigate with orders.csv if counts differ.

## Related skills

- `potions-demo-status` — heartbeats / open positions
- `potions-oanda-reconcile` — broker account sync (positions), not plugin trade tape
- `potions-quick-backtest` — research replays under `live/state/`
- `potions-repo-router` — task routing
