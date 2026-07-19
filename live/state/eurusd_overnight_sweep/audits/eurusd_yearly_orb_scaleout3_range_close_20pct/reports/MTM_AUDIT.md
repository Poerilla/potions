# EURUSD Yearly ORB scaleout3 20% range-close

| Metric | Value |
|---|---:|
| Source | `live/state/eurusd_overnight_sweep/states/eurusd_yearly_orb_scaleout3_range_close_20pct/fills.csv` |
| Bar source | `live/state/eurusd_overnight_sweep/states/eurusd_yearly_orb_scaleout3_range_close_20pct/bars/EURUSD_D.csv` |
| Bar window | `2003-05-06` to `2026-03-31` |
| Units | 183 |
| Trade groups | 61 |
| Winning units | 70 |
| Losing units | 113 |
| Net points | 1.26 |
| Point value | $100000.00 |
| Net dollars | $124,518.75 |
| Close MTM DD | $-45,705.75 |
| Intrabar stress MTM DD | $-47,959.25 |
| Max open units | 3 |
| Net / intrabar stress DD | 2.60 |

Notes: Broker-like daily StrategyPlugin replay. OCO stop entries arm both yearly boundaries and range-close exits require a close 20% back into the yearly ORB. EURUSD overnight sweep; fee=$7.00/unit.
