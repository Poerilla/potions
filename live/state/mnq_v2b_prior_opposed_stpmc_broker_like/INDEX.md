# MNQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session MNQ hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 353 | 1765 | $113547.50 | $-5340.50 | $-5418.00 | 68.56 | 2.524 | 20.96 |

## Validation

- Regime sessions replayed: **1,164**.
- Causal gate audit: **353 / 353** v2b entry fills had an earlier same-session MNQ hourly ST+PMC entry in the opposite direction.
- Violations found: **0**.
- Direction mix: **205 Short** v2b campaigns and **148 Long** v2b campaigns.
- ST+PMC source: `mnq_hourly_st_pmc_sl25_tp75_3r`.
- Sizing: `S_1_1_3` (`entry_qty=5`, `tp1_qty=1`, `tp2_qty=1`, runner `3`).
- Visual validation: [`charts/prior_opposed_15m/INDEX.md`](charts/prior_opposed_15m/INDEX.md) contains **353** 15m MNQ campaign charts with same-session ST+PMC trades and the v2b campaign overlaid.
- Robustness audit: [`robustness_audit/ROBUSTNESS_AUDIT.md`](robustness_audit/ROBUSTNESS_AUDIT.md) attacks yearly stability, rolling PF, concentration, runner dependency, gap-through cost, OR-width quartiles, and recovery duration.
- Filter study: [`robustness_audit/FILTER_STUDY.md`](robustness_audit/FILTER_STUDY.md) tests skip/reduce-size rules for wide OR, large gaps, 2022, and top-winner deletion.
- Event calendar audit: [`robustness_audit/EVENT_CALENDAR_AUDIT.md`](robustness_audit/EVENT_CALENDAR_AUDIT.md) tests free official CPI/FOMC dates.
- Execution scrutiny: [`../v2b_prior_opposed_execution_scrutiny/mnq/SCRUTINY_REPORT.md`](../v2b_prior_opposed_execution_scrutiny/mnq/SCRUTINY_REPORT.md) compares fill-book causality, 1m latency buckets, and tick-replay manifest needs.

## Read

This confirms MNQ prior-opposed is no longer just a filtered research-tape mirror. Like the NQ path, it is a strict delayed-arming StrategyPlugin replay: if same-session ST+PMC fires in one direction, v2b may later arm only the opposite boundary. The MNQ result is smaller in dollars than NQ but very close in shape: 353 campaigns versus NQ's 352, 0 causality violations, and nearly identical 1m timing-risk buckets.

The main caveat also matches NQ: it is not tick-proven yet. The 1m execution scrutiny routes same-minute and pre-arm-touch campaigns to `tick_replay_manifest.csv` for tick/broker reconstruction before live funding.

Files:

- `summary.csv`
- `states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- `charts/prior_opposed_15m/INDEX.md`
- `robustness_audit/ROBUSTNESS_AUDIT.md`
- `robustness_audit/FILTER_STUDY.md`
- `robustness_audit/EVENT_CALENDAR_AUDIT.md`
