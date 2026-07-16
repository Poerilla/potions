# MYM v2b Prior-Opposed Resting-Limit (hour-complete)

True `Engine + PaperBroker + StrategyPlugin` replay. Arms v2b only after the
same-session opposite ST+PMC entry limit is **knowably resting** at
**hour-complete** (`live_after_ts + 1h`).

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 423 | 2115 | $22,101.38 | $-3,386.75 | **$-3,416.75** | 60.52 | 1.456 | **6.47** |

## Causality / gate

- Gate mode: **resting_limit** (hour-complete)
- Prior-opposite entries: **423 / 423**
- Causal violations: **0**
- Direction mix: **194 long / 229 short**

## vs legacy hourly fill stamp

| Metric | Hour-complete resting | Legacy fill stamp |
|---|---:|---:|
| Campaigns | 423 | 338 |
| Net | $22,101.38 | $26,088.62 |
| MTM stress | $-3,416.75 | $-2,694.62 |
| Net/Stress | 6.47 | 9.68 |

Legacy folder (diagnostic): [`../mym_v2b_prior_opposed_stpmc_broker_like/`](../mym_v2b_prior_opposed_stpmc_broker_like/INDEX.md).

Cross-market table: [`../v2b_prior_opposed_resting_limit_cross_market/INDEX.md`](../v2b_prior_opposed_resting_limit_cross_market/INDEX.md).

Files:

- `summary.csv`
- `states/`
