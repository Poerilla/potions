# MYM Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mym_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mym_monthly_orb_restricted_scaleout3_boundary_stop/bars/MYM_D.csv` |
| Bar window | `2019-05-05` to `2026-03-08` |
| Units | 18 |
| Trade groups | 6 |
| Winning units | 9 |
| Losing units | 6 |
| Net points | -54685.50 |
| Point value | $0.50 |
| Net dollars | $-27,342.75 |
| Close MTM DD | $-48,244.50 |
| Intrabar stress MTM DD | $-48,570.00 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.56 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
