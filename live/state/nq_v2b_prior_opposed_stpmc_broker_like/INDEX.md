# NQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session NQ hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 352 | 1760 | $1184585.00 | $-53172.00 | $-53847.00 | 69.32 | 2.654 | 22.00 |

## Validation

- Causal gate audit: **352 / 352** v2b entry fills had an earlier same-session NQ hourly ST+PMC entry in the opposite direction.
- Violations found: **0**.
- Direction mix: **205 Short** v2b campaigns and **147 Long** v2b campaigns.
- ST+PMC source: `nq_hourly_st_pmc_sl25_tp75_3r`.
- Sizing: `S_1_1_3` (`entry_qty=5`, `tp1_qty=1`, `tp2_qty=1`, runner `3`).
- Visual validation: [`charts/prior_opposed_15m/INDEX.md`](charts/prior_opposed_15m/INDEX.md) contains **352** 15m NQ campaign charts with same-session ST+PMC trades and the v2b campaign overlaid.
- Robustness audit: [`robustness_audit/ROBUSTNESS_AUDIT.md`](robustness_audit/ROBUSTNESS_AUDIT.md) attacks yearly stability, rolling PF, concentration, runner dependency, gap-through cost, OR-width quartiles, and recovery duration.
- Filter study: [`robustness_audit/FILTER_STUDY.md`](robustness_audit/FILTER_STUDY.md) tests skip/reduce-size rules for wide OR, large gaps, 2022, and top-winner deletion.
- Event calendar audit: [`robustness_audit/EVENT_CALENDAR_AUDIT.md`](robustness_audit/EVENT_CALENDAR_AUDIT.md) tests free official CPI/FOMC dates.

## Read

This confirms the prior-opposed signal is not just a reconstructed unit-tape artifact. The full StrategyPlugin replay is stronger than the earlier screening row because it is a delayed arming rule: if ST+PMC fires first in one direction, v2b may still arm the opposite boundary later in the same session. That creates a different, live-orderable path than simply filtering the original all-day v2b tape.

Files:

- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- `charts/prior_opposed_15m/INDEX.md`
- `robustness_audit/ROBUSTNESS_AUDIT.md`
- `robustness_audit/FILTER_STUDY.md`
- `robustness_audit/EVENT_CALENDAR_AUDIT.md`
