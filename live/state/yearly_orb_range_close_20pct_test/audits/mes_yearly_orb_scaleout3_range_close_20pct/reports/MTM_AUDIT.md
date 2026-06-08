# MES Yearly ORB scaleout3 20% range-close

| Metric | Value |
|---|---:|
| Source | `potions/live/state/yearly_orb_range_close_20pct_test/states/mes_yearly_orb_scaleout3_range_close_20pct/fills.csv` |
| Bar source | `potions/live/state/yearly_orb_range_close_20pct_test/states/mes_yearly_orb_scaleout3_range_close_20pct/bars/MES_D.csv` |
| Bar window | `2019-05-05` to `2023-08-17` |
| Units | 33 |
| Trade groups | 11 |
| Winning units | 13 |
| Losing units | 20 |
| Net points | 2099.06 |
| Point value | $5.00 |
| Net dollars | $10,495.31 |
| Close MTM DD | $-7,597.50 |
| Intrabar stress MTM DD | $-8,497.50 |
| Max open units | 3 |
| Net / intrabar stress DD | 1.24 |

Notes: Broker-like daily StrategyPlugin replay. OCO stop entries arm both yearly boundaries and range-close exits require a close 20% back into the yearly ORB. Open units marked at final replay close.
