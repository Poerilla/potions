# YM v2b Prior-Opposed ST+PMC Broker-Like Replay

**2026-07-16:** Legacy hourly **fill-stamp** book (diagnostic). Promotion path is hour-complete resting-limit: [`../ym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md`](../ym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md).


True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session YM hourly ST+PMC entry has already fired in the opposite direction.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 351 | 1755 | $318791.25 | $-26185.00 | $-26910.00 | 59.54 | 1.841 | 11.85 |

## Causality

- Regime sessions replayed: **1182**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **351 / 351**
- Causal violations: **0**
- Direction mix: **152 long / 199 short**

Files:

- `summary.csv`
- `states/ym_v2b_prior_opposed_stpmc_only_S_1_1_3/`