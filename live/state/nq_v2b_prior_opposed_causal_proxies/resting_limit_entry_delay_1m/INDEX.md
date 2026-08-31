# NQ v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay (resting_limit)

True `Engine + PaperBroker + StrategyPlugin` replay.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 431 | 2155 | $1326222.50 | $-70485.00 | $-70985.00 | 65.20 | 2.344 | 18.68 |

## Causality / gate

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Gate mode: **resting_limit**
- Prior-opposite entries found: **431 / 431**
- Causal violations: **0**
- Direction mix: **186 long / 245 short**
- Entry stop live_after delay: **1.00** minutes after arm decision (stop cannot fill on the immediate next 1m bar)

Files:

- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`