# NQ v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay (resting_limit)

True `Engine + PaperBroker + StrategyPlugin` replay.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1279 | 6395 | $878900.00 | $-97092.25 | $-97692.25 | 54.42 | 1.253 | 9.00 |

## Causality / gate

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Gate mode: **resting_limit**
- Prior-opposite entries found: **323 / 1279**
- Causal violations: **0**
- Direction mix: **660 long / 619 short**
- Invalidate without opposite ST within **60** minutes of entry

Files:

- `summary.csv`
- `states/nq_v2b_provisional_stpmc_S_1_1_3/`