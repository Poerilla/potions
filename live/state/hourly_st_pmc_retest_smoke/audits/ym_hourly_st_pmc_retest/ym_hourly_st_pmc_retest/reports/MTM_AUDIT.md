# YM Hourly ST + PMC Retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `potions/live/state/hourly_st_pmc_retest_smoke/states/ym_hourly_st_pmc_retest/fills.csv` |
| Bar source | `/home/tester/hsm/potions/ym/raw/glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2011-03-30T02:00:00-04:00` |
| Units | 63 |
| Trade groups | 63 |
| Winning units | 15 |
| Losing units | 48 |
| Net points | -315.28 |
| Point value | $5.00 |
| Net dollars | $-1,670.89 |
| Close MTM DD | $-4,379.68 |
| Intrabar stress MTM DD | $-4,444.68 |
| Max open units | 1 |
| Net / intrabar stress DD | -0.38 |

Notes: Hardened StrategyPlugin replay via Engine + PaperBroker. Hourly limit at ST stop filtered by prior month close; 50 pt stop / 150 pt target; slippage=1 tick; fee=$1.50/unit.
