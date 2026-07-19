# EURUSD v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session EURUSD hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 370 | 1850 | $-9475.00 | $-20901.00 | $-21021.00 | 38.38 | 0.918 | -0.45 |

## Causality

- Regime sessions replayed: **1623**
- Replay start: **2015-01-02**
- Prior-opposite entries found: **370 / 370**
- Causal violations: **0**
- Direction mix: **184 long / 186 short**

Files:

- `summary.csv`
- `states/eurusd_v2b_prior_opposed_stpmc_only_S_1_1_3/`