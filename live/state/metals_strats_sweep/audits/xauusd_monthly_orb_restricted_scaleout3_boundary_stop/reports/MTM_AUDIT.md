# XAUUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/metals_strats_sweep/states/xauusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/metals_strats_sweep/states/xauusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/XAUUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1890 |
| Trade groups | 630 |
| Winning units | 749 |
| Losing units | 1141 |
| Net points | 2418.34 |
| Point value | $100.00 |
| Net dollars | $228,603.87 |
| Close MTM DD | $-189,199.50 |
| Intrabar stress MTM DD | $-194,815.50 |
| Max open units | 3 |
| Net / intrabar stress DD | 1.17 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.
