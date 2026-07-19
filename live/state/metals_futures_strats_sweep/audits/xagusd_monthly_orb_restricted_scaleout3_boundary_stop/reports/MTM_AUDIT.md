# XAGUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/metals_futures_strats_sweep/states/xagusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/metals_futures_strats_sweep/states/xagusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/XAGUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1917 |
| Trade groups | 639 |
| Winning units | 701 |
| Losing units | 1216 |
| Net points | -37.23 |
| Point value | $1000.00 |
| Net dollars | $-40,106.50 |
| Close MTM DD | $-132,082.50 |
| Intrabar stress MTM DD | $-139,147.50 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.29 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.
