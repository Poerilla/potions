# ES v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session ES hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 245 | 1225 | $348687.50 | $-33113.50 | $-33163.50 | 63.67 | 2.084 | 10.51 |

## Causality

- Regime sessions replayed: **953**
- Prior-opposite entries found: **245 / 245**
- Causal violations: **0**
- Direction mix: **107 long / 138 short**

Files:

- `summary.csv`
- `states/es_v2b_prior_opposed_stpmc_only_S_1_1_3/`