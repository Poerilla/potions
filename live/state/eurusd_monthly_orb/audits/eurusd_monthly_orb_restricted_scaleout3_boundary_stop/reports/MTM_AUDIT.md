# EURUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/eurusd_monthly_orb/states/eurusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/eurusd_monthly_orb/states/eurusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/EURUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1965 |
| Trade groups | 655 |
| Winning units | 742 |
| Losing units | 1223 |
| Net points | -1.39 |
| Point value | $100000.00 |
| Net dollars | $-153,062.50 |
| Close MTM DD | $-164,174.50 |
| Intrabar stress MTM DD | $-164,402.50 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.93 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. fee=$7.00/unit.
