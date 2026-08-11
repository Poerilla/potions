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
| Asia-range London (USDJPY) | `live/fx_v2b_asia_range_london.py`, `…_usdjpy_sizing`, `…_usdjpy_filters`, `…_usdjpy_validation` | Research/practice promote: filtered `S_3_1_3` — `FILTERS.md`; funded-sleeve gates: `VALIDATION_GATES.md` |
| Prior-opposed v2b | `live/nq_v2b_prior_opposed_replay.py` (+ family drivers) | Resting-limit = promotion gate |

### Decision filters (use when tuning sit-outs)

Before promoting a London/Asia or similar campaign sleeve, check:

1. **Calendar months** that are consistently negative across years (`neg_frac_years` + mean year net) → `skip_entry_months` (same idea as Monday OR Aug/Sep).
2. **Shadow rolling WR/PF** on the **unfiltered** campaign tape (default window 50, WR≥40%, PF≥1). Taken-only windows freeze after the first PF dip — see `live/asia_range_shadow.py` and `live/state/fx_v2b_asia_range_london_usdjpy_filters/FILTERS.md`. First 50 campaigns are roll-gate warmup unless the shadow book is pre-seeded.
3. **Funded-sleeve hardening** before calling it funded capital: frozen-rule OOS, walk-forward yearly/anchors, Jan/WR/PF attribution, path-aware risk logs, live-parity `campaign_parity.csv` vs research decision tape — driver `live/fx_v2b_asia_range_london_usdjpy_validation.py` → `VALIDATION_GATES.md`.

Argue rankings with **filtered** broker-like N/S when those gates are part of the live book (example: unfiltered Asia-range ~2.1 → filtered `S_3_1_3` **7.23**). Document the shadow contract in the study hub (`FILTERS.md` pattern) and update STRATEGY_TRACKER + CHANGE_LOG via `potions-tracker-docs`.

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
