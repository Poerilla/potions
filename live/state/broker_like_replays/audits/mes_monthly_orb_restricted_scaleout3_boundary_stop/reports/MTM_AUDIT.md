# MES Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/bars/MES_D.csv` |
| Bar window | `2019-05-05` to `2023-08-17` |
| Units | 333 |
| Trade groups | 111 |
| Winning units | 149 |
| Losing units | 184 |
| Net points | 2313.06 |
| Point value | $5.00 |
| Net dollars | $11,065.81 |
| Close MTM DD | $-7,563.75 |
| Intrabar stress MTM DD | $-8,170.50 |
| Max open units | 3 |
| Net / intrabar stress DD | 1.35 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. Open units marked at final replay close. Slippage=1 tick(s), fee=$1.50/unit.
