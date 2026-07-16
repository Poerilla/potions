# MNQ v2b Prior-Opposed Resting-Limit (hour-complete)

True `Engine + PaperBroker + StrategyPlugin` replay. Arms v2b only after the
same-session opposite ST+PMC entry limit is **knowably resting** at
**hour-complete** (`live_after_ts + 1h`).

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 428 | 2140 | $128,360.50 | $-6,905.00 | **$-6,960.00** | 65.42 | 2.257 | **18.44** |

## Causality / gate

- Gate mode: **resting_limit** (hour-complete)
- Prior-opposite entries: **428 / 428**
- Causal violations: **0**
- Direction mix: **183 long / 245 short**

## vs legacy hourly fill stamp

| Metric | Hour-complete resting | Legacy fill stamp |
|---|---:|---:|
| Campaigns | 428 | 352 |
| Net | $128,360.50 | $114,970.50 |
| MTM stress | $-6,960.00 | $-5,427.50 |
| Net/Stress | 18.44 | 21.18 |

Legacy folder (diagnostic): [`../mnq_v2b_prior_opposed_stpmc_broker_like/`](../mnq_v2b_prior_opposed_stpmc_broker_like/INDEX.md).

Cross-market table: [`../v2b_prior_opposed_resting_limit_cross_market/INDEX.md`](../v2b_prior_opposed_resting_limit_cross_market/INDEX.md).

Files:

- `summary.csv`
- `states/`
