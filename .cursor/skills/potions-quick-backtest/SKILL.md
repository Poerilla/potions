---
name: potions-quick-backtest
description: >-
  Runs quick potions backtests and broker-like StrategyPlugin replays.
  Use when the user asks for a quick backtest, PaperBroker replay, fair
  benchmark, broker-like ranking, or family driver under live/.
---

# Quick backtests / replays

Prefer **StrategyPlugin + Engine + PaperBroker** for anything that might promote. Pandas/research scripts are diagnostic unless rebuilt on the plugin path.

Workspace ranking layers: [`README.md`](../../../README.md).

## Entry points

| Goal | Command / module | Notes |
|------|------------------|-------|
| CLI replay | `python3 -m potions.live.cli replay …` | See `live/cli.py` |
| Cross-strategy broker-like table | `live/broker_like_replays.py` | Generated table hub: `live/state/broker_like_replays/` |
| Signal-only ranking | `live/signal_replays.py` | Weaker; not promotion |
| Production-canonical ORB OCO | `scripts/step2_preplaced_stops.py` | Legacy plumbing reference |
| Fair capital / max-stress | `scripts/top_strat_fair_benchmark.py` | → `TOP_STRATS.md` |
| ST+PMC variants | `live/hourly_st_pmc_strategyplugin_variants.py`, `live/st_pmc_1mfill_cross_market.py` | Cross-market hubs under `live/state/` |
| Monday OR FX | `live/fx_monday_or_breakout_broker.py`, `live/monday_or_sizing_sweep_broker.py` | Phase hubs under `live/state/monday_or_*` |
| Prior-opposed v2b | `live/nq_v2b_prior_opposed_replay.py` (+ family drivers) | Resting-limit = promotion gate |

Typical env:

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
```

## Artifact layout

Write under `live/state/<slug>/`:

- `SUMMARY.md` / `summary.csv`
- equities / unit fills
- audits / charts as needed

Do **not** put research replays under `live/demo/` (demos are continuous runners only).

## After a material run

1. Causality / realism if promotion-relevant → `potions-causality-audit`
2. Update tracker + CHANGE_LOG + study SUMMARY → `potions-tracker-docs`
3. Large regenerable dumps stay local/Drive → `potions-git-backup` (don’t git-add multi-GB)

## Related skills

- `potions-strategy-plugin` — new plugin before first replay
- `potions-causality-audit` — lookahead / known-answer checks
- `potions-tracker-docs` — publish results in tracker hubs
