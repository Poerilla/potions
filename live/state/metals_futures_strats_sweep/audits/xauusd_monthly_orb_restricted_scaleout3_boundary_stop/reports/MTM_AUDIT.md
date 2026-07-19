# XAUUSD Monthly ORB restricted scaleout3 boundary-stop entry

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/metals_futures_strats_sweep/states/xauusd_monthly_orb_restricted_scaleout3_boundary_stop/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/metals_futures_strats_sweep/states/xauusd_monthly_orb_restricted_scaleout3_boundary_stop/bars/XAUUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 1890 |
| Trade groups | 630 |
| Winning units | 750 |
| Losing units | 1140 |
| Net points | 2500.01 |
| Point value | $100.00 |
| Net dollars | $247,166.10 |
| Close MTM DD | $-189,177.50 |
| Intrabar stress MTM DD | $-194,793.50 |
| Max open units | 3 |
| Net / intrabar stress DD | 1.27 |

Notes: Broker-like daily StrategyPlugin replay. After the monthly OR forms, resting boundary stop entries try to catch clean breaks; failed breaks flatten when close retraces 25% back into the OR.
