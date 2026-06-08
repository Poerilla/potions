# ES Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/es_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/es_monthly_orb_restricted_scaleout3_boundary_stop/bars/ES_D.csv` |
| Bar window | `2010-06-06` to `2026-03-08` |
| Units | 12 |
| Trade groups | 4 |
| Winning units | 8 |
| Losing units | 3 |
| Net points | 5621.50 |
| Point value | $50.00 |
| Net dollars | $281,075.00 |
| Close MTM DD | $-62,075.00 |
| Intrabar stress MTM DD | $-66,162.50 |
| Max open units | 3 |
| Net / intrabar stress DD | 4.25 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
