# YM v2b Prior-Opposed Resting-Limit (hour-complete)

True `Engine + PaperBroker + StrategyPlugin` replay. Arms v2b only after the
same-session opposite ST+PMC entry limit is **knowably resting** at
**hour-complete** (`live_after_ts + 1h`).

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 436 | 2180 | $289,225.00 | $-33,325.00 | **$-33,893.75** | 61.01 | 1.593 | **8.53** |

## Causality / gate

- Gate mode: **resting_limit** (hour-complete)
- Prior-opposite entries: **436 / 436**
- Causal violations: **0**
- Direction mix: **199 long / 237 short**

## vs legacy hourly fill stamp

| Metric | Hour-complete resting | Legacy fill stamp |
|---|---:|---:|
| Campaigns | 436 | 351 |
| Net | $289,225.00 | $318,791.25 |
| MTM stress | $-33,893.75 | $-26,910.00 |
| Net/Stress | 8.53 | 11.85 |

Legacy folder (diagnostic): [`../ym_v2b_prior_opposed_stpmc_broker_like/`](../ym_v2b_prior_opposed_stpmc_broker_like/INDEX.md).

Cross-market table: [`../v2b_prior_opposed_resting_limit_cross_market/INDEX.md`](../v2b_prior_opposed_resting_limit_cross_market/INDEX.md).

Files:

- `summary.csv`
- `states/`
