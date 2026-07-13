# MYM v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session MYM hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 338 | 1690 | $26088.62 | $-2657.12 | $-2694.62 | 59.76 | 1.703 | 9.68 |

## Causality

- Regime sessions replayed: **1160**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **338 / 338**
- Causal violations: **0**
- Direction mix: **144 long / 194 short**

Files:

- `summary.csv`
- `states/mym_v2b_prior_opposed_stpmc_only_S_1_1_3/`