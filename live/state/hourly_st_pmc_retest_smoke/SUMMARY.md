# YM Hourly ST + PMC StrategyPlugin Replay

Live-orderable path through `Engine + PaperBroker` with realism defaults.

| Metric | Value |
|---|---:|
| Trades | 63 |
| Units | 63 |
| Win rate | 23.8% |
| Net USD | $-1,670.89 |
| Profit factor | 0.31 |
| Closed DD USD | $-4,379.68 |
| Intrabar stress DD USD | $-4,444.68 |
| Net / stress | -0.38 |

State root: `potions/live/state/hourly_st_pmc_retest_smoke/states/ym_hourly_st_pmc_retest`

Hardened StrategyPlugin replay via Engine + PaperBroker. Hourly limit at ST stop filtered by prior month close; 50 pt stop / 150 pt target; slippage=1 tick; fee=$1.50/unit.
