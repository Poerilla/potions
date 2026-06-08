# MNQ Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mnq_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mnq_monthly_orb_restricted_scaleout3_boundary_stop/bars/MNQ_D.csv` |
| Bar window | `2019-05-05` to `2026-03-08` |
| Units | 471 |
| Trade groups | 157 |
| Winning units | 278 |
| Losing units | 159 |
| Net points | 19794.75 |
| Point value | $2.00 |
| Net dollars | $39,589.50 |
| Close MTM DD | $-16,119.50 |
| Intrabar stress MTM DD | $-17,330.25 |
| Max open units | 3 |
| Net / intrabar stress DD | 2.28 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
