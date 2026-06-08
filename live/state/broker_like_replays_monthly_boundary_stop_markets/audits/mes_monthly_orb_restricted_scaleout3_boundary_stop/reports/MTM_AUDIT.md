# MES Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/bars/MES_D.csv` |
| Bar window | `2019-05-05` to `2023-08-17` |
| Units | 21 |
| Trade groups | 7 |
| Winning units | 10 |
| Losing units | 7 |
| Net points | -3522.38 |
| Point value | $5.00 |
| Net dollars | $-17,611.88 |
| Close MTM DD | $-38,936.25 |
| Intrabar stress MTM DD | $-39,266.25 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.45 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
