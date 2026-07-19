# EURUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `live/state/eurusd_overnight_sweep/states/eurusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `live/state/eurusd_overnight_sweep/states/eurusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/EURUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1956 |
| Trade groups | 652 |
| Winning units | 746 |
| Losing units | 1210 |
| Net points | -1.27 |
| Point value | $100000.00 |
| Net dollars | $-140,782.25 |
| Close MTM DD | $-157,242.50 |
| Intrabar stress MTM DD | $-158,514.50 |
| Max open units | 3 |
| Net / intrabar stress DD | -0.89 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR. EURUSD overnight sweep; fee=$7.00/unit.
