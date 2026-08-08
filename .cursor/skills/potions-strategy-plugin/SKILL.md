---
name: potions-strategy-plugin
description: >-
  Creates and registers a new potions StrategyPlugin under live/strategies.
  Use when adding a strategy plugin, registering strategy_type, wiring
  live_after_ts, or extending the Engine/PaperBroker plugin contract.
---

# New StrategyPlugin

Read first: [`live/Platform.md`](../../../live/Platform.md) §§5, 7, 13.  
Base: [`live/strategies/base.py`](../../../live/strategies/base.py)  
Registry: [`live/registry.py`](../../../live/registry.py)

## Checklist

1. **Class** under `live/strategies/<name>.py`
   - Subclass `StrategyPlugin`
   - Set unique `strategy_type` string
   - Implement `on_bar_close` / `on_fill` as needed
2. **Register**
   - Import + map in `live/registry.py`
   - Export from `live/strategies/__init__.py` if that module re-exports plugins
3. **Causality**
   - Every intent: `live_after_ts` = confirming bar timestamp
   - Use only features with `available_at_ts <= current_bar_ts`
   - Prefer `available_at_ts` over raw left-label HTF `ts` for gates
4. **Driver / ranking row**
   - Add broker-like row in `live/broker_like_replays.py` **or** a dedicated `live/<family>_*.py` driver
   - Write artifacts under `live/state/<slug>/`
5. **DSR ledger before peek**
   - Append a row to `data/validation/dsr_trial_ledger.csv` **before** reviewing results
6. **Tier-1?**
   - Update Platform.md §5 table
   - Add/update falsification row in [`live/specs/CAUSAL_GRAPH.md`](../../../live/specs/CAUSAL_GRAPH.md)
   - Same-PR Platform Maintenance rule if contract/fill/causality changes

## Good examples

| Plugin | File |
|--------|------|
| V2B scaleout | `live/strategies/v2b_scaleout.py` |
| Hourly ST+PMC | `live/strategies/hourly_st_pmc_retest.py` |
| Monday OR | `live/strategies/monday_or_breakout.py` |
| Yearly ORB | `live/strategies/yearly_orb.py` |
| Trend momentum | `live/strategies/trend_momentum.py` |

## After create

- Quick replay: `potions-quick-backtest`
- Causality check: `potions-causality-audit`
- Tracker / CHANGE_LOG: `potions-tracker-docs`

## Related skills

- `potions-repo-router` — when to open Platform.md
- `potions-quick-backtest` — run first broker-like pass
- `potions-causality-audit` — feature / gate audits
- `potions-tracker-docs` — doc sync after promotion work
