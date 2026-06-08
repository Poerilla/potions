# YM v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session YM hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 347 | 1735 | $320190.00 | $-26110.00 | $-26835.00 | 59.65 | 1.855 | 11.93 |

## Causality

- Regime sessions replayed: **944**
- Prior-opposite entries found: **347 / 347**
- Causal violations: **0**
- Direction mix: **151 long / 196 short**

Files:

- `summary.csv`
- `states/ym_v2b_prior_opposed_stpmc_only_S_1_1_3/`