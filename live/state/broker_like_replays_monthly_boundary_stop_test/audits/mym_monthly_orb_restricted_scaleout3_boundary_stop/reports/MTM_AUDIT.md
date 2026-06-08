# MYM Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/mym_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/mym_monthly_orb_restricted_scaleout3_boundary_stop/bars/MYM_D.csv` |
| Bar window | `2019-05-05` to `2026-03-08` |
| Units | 564 |
| Trade groups | 188 |
| Winning units | 257 |
| Losing units | 280 |
| Net points | 42706.50 |
| Point value | $0.50 |
| Net dollars | $21,353.25 |
| Close MTM DD | $-4,626.62 |
| Intrabar stress MTM DD | $-5,504.12 |
| Max open units | 3 |
| Net / intrabar stress DD | 3.88 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. Open units marked at final replay close.
