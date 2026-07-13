# NQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session NQ hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 352 | 1760 | $1175785.00 | $-53267.00 | $-53942.00 | 69.32 | 2.633 | 21.80 |

## Causality

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **352 / 352**
- Causal violations: **0**
- Direction mix: **147 long / 205 short**

Files:

- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`