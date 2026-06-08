# YM Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/ym_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/ym_monthly_orb_restricted_scaleout3_boundary_stop/bars/YM_D.csv` |
| Bar window | `2010-06-06` to `2026-05-06` |
| Units | 6 |
| Trade groups | 2 |
| Winning units | 2 |
| Losing units | 3 |
| Net points | -120588.50 |
| Point value | $5.00 |
| Net dollars | $-602,942.50 |
| Close MTM DD | $-612,810.00 |
| Intrabar stress MTM DD | $-616,650.00 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.98 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
