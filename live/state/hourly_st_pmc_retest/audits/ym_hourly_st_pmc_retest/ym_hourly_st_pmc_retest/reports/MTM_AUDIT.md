# YM Hourly ST + PMC Retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/hourly_st_pmc_retest/states/ym_hourly_st_pmc_retest/fills.csv` |
| Bar source | `/home/tester/hsm/potions/ym/raw/glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-05-06T19:00:00-04:00` |
| Units | 1841 |
| Trade groups | 1841 |
| Winning units | 537 |
| Losing units | 1304 |
| Net points | 12999.76 |
| Point value | $5.00 |
| Net dollars | $62,237.29 |
| Close MTM DD | $-16,358.18 |
| Intrabar stress MTM DD | $-16,416.88 |
| Max open units | 1 |
| Net / intrabar stress DD | 3.79 |

Notes: Hardened StrategyPlugin replay via Engine + PaperBroker. Hourly limit at ST stop filtered by prior month close; 50 pt stop / 150 pt target; slippage=1 tick; fee=$1.50/unit.
