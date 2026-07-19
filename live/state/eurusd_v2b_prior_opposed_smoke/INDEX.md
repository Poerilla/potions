# EURUSD v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session EURUSD hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | 60 | $4097.00 | $-2724.00 | $-2804.00 | 50.00 | 2.618 | 1.46 |

## Causality

- Regime sessions replayed: **60**
- Replay start: **2024-01-02**
- Prior-opposite entries found: **12 / 12**
- Causal violations: **0**
- Direction mix: **7 long / 5 short**

Files:

- `summary.csv`
- `states/eurusd_v2b_prior_opposed_stpmc_only_S_1_1_3/`