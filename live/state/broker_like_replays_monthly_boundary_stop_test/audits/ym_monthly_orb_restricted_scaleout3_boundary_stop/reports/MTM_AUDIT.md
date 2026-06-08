# YM Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/ym_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `potions/live/state/broker_like_replays_monthly_boundary_stop_test/states/ym_monthly_orb_restricted_scaleout3_boundary_stop/bars/YM_D.csv` |
| Bar window | `2010-06-06` to `2026-05-06` |
| Units | 1296 |
| Trade groups | 432 |
| Winning units | 579 |
| Losing units | 638 |
| Net points | 71905.25 |
| Point value | $5.00 |
| Net dollars | $359,526.25 |
| Close MTM DD | $-45,127.50 |
| Intrabar stress MTM DD | $-47,753.75 |
| Max open units | 3 |
| Net / intrabar stress DD | 7.53 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. Open units marked at final replay close.
