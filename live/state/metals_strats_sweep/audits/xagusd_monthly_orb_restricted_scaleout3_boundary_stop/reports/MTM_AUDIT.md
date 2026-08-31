# XAGUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/metals_strats_sweep/states/xagusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/metals_strats_sweep/states/xagusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/XAGUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1917 |
| Trade groups | 639 |
| Winning units | 696 |
| Losing units | 1221 |
| Net points | -44.70 |
| Point value | $5000.00 |
| Net dollars | $-236,940.25 |
| Close MTM DD | $-660,409.00 |
| Intrabar stress MTM DD | $-695,734.00 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.34 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.
