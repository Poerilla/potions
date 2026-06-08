# MYM v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session MYM hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 333 | 1665 | $26053.62 | $-2627.38 | $-2664.88 | 59.76 | 1.710 | 9.78 |

## Causality

- Regime sessions replayed: **925**
- Prior-opposite entries found: **333 / 333**
- Causal violations: **0**
- Direction mix: **142 long / 191 short**

Files:

- `summary.csv`
- `states/mym_v2b_prior_opposed_stpmc_only_S_1_1_3/`