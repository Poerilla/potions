# MES Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/bars/MES_D.csv` |
| Bar window | `2019-05-05` to `2023-08-17` |
| Units | 333 |
| Trade groups | 111 |
| Winning units | 164 |
| Losing units | 150 |
| Net points | 4437.31 |
| Point value | $5.00 |
| Net dollars | $22,186.56 |
| Close MTM DD | $-6,030.94 |
| Intrabar stress MTM DD | $-7,267.19 |
| Max open units | 3 |
| Net / intrabar stress DD | 3.05 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. Open units marked at final replay close.
