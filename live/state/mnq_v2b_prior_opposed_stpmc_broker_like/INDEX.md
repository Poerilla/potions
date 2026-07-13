# MNQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session MNQ hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 352 | 1760 | $114970.50 | $-5350.00 | $-5427.50 | 68.47 | 2.540 | 21.18 |

## Causality

- Regime sessions replayed: **1160**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **352 / 352**
- Causal violations: **0**
- Direction mix: **148 long / 204 short**

Files:

- `summary.csv`
- `states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/`