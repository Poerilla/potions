# MES Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays/states/mes_monthly_orb_restricted_scaleout3_boundary_stop/bars/MES_D.csv` |
| Bar window | `2019-05-05` to `2023-08-17` |
| Units | 336 |
| Trade groups | 112 |
| Winning units | 149 |
| Losing units | 187 |
| Net points | 2037.81 |
| Point value | $5.00 |
| Net dollars | $9,685.06 |
| Close MTM DD | $-9,229.50 |
| Intrabar stress MTM DD | $-9,836.25 |
| Max open units | 3 |
| Net / intrabar stress DD | 0.98 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. Open units marked at final replay close. Slippage=1 tick(s), fee=$1.50/unit.
