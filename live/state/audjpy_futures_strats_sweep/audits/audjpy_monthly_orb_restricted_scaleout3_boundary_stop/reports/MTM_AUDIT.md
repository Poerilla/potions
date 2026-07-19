# AUDJPY Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/audjpy_futures_strats_sweep/states/audjpy_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/audjpy_futures_strats_sweep/states/audjpy_monthly_orb_restricted_scaleout3_boundary_stop/bars/AUDJPY_D.csv` |
| Bar window | `2003-12-02` to `2026-03-31` |
| Units | 1848 |
| Trade groups | 616 |
| Winning units | 746 |
| Losing units | 1102 |
| Net points | 33.15 |
| Point value | $100000.00 |
| Net dollars | $3,302,239.00 |
| Close MTM DD | $-7,192,045.00 |
| Intrabar stress MTM DD | $-7,459,045.00 |
| Max open units | 3 |
| Net / intrabar stress DD | 0.44 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.
