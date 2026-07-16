# NQ v2b Prior-Opposed Resting-Limit Gate (causal baseline)

True `Engine + PaperBroker + StrategyPlugin` replay. Arms v2b only after the
same-session opposite ST+PMC **entry limit is knowably resting**.

ST+PMC decides on completed left-labeled hours. Gate availability is
**`live_after_ts + 1h`** (hour-complete), not the left-label stamp. That removes
the left-label lookahead while keeping ST’s own order semantics unchanged.

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 432 | 2160 | **$1,330,920** | $-68,110 | **$-68,610** | 65.97 | 2.326 | **19.40** |

## Causality / gate

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Gate mode: **resting_limit** (hour-complete availability)
- Prior-opposite entries found: **432 / 432**
- Causal violations: **0**
- Direction mix: **186 long / 246 short**
- Filters: **432 / 1164** regime days

## vs left-label diagnostic

Left-label book (lookahead): [`../resting_limit_left_label_diagnostic/`](../resting_limit_left_label_diagnostic/)
— **434** / **$1,321,745** / **19.26** Net/Stress.

Causal hour-complete baseline is **slightly better**, not worse. Early-sleeve
recovery analysis: [`../early_pnl_recovery/INDEX.md`](../early_pnl_recovery/INDEX.md).

Files:

- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
