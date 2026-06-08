# NQ Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/nq_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_markets/states/nq_monthly_orb_restricted_scaleout3_boundary_stop/bars/NQ_D.csv` |
| Bar window | `2010-06-06` to `2026-03-08` |
| Units | 18 |
| Trade groups | 6 |
| Winning units | 10 |
| Losing units | 5 |
| Net points | 22310.38 |
| Point value | $20.00 |
| Net dollars | $446,207.50 |
| Close MTM DD | $-117,565.00 |
| Intrabar stress MTM DD | $-122,080.00 |
| Max open units | 3 |
| Net / intrabar stress DD | 3.66 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks are closed on range-close logic. Open units marked at final replay close.
