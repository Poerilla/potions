# YM Hourly ST + PMC StrategyPlugin Replay

Live-orderable path through `Engine + PaperBroker` with realism defaults.

| Metric | Value |
|---|---:|
| Trades | 1841 |
| Units | 1841 |
| Win rate | 29.2% |
| Net USD | $62,237.29 |
| Profit factor | 1.18 |
| Closed DD USD | $-16,358.18 |
| Intrabar stress DD USD | $-16,416.88 |
| Net / stress | 3.79 |

State root: `/home/tester/hsm/potions/live/state/hourly_st_pmc_retest/states/ym_hourly_st_pmc_retest`

Hardened StrategyPlugin replay via Engine + PaperBroker. Hourly limit at ST stop filtered by prior month close; 50 pt stop / 150 pt target; slippage=1 tick; fee=$1.50/unit.
