# EURUSD 15m ST DCA 0.5×5 exit=close

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/eurusd_intraday_st_dca_broker/states/eurusd_intraday_st_dca_15m_0p5x5_close/fills.csv` |
| Bar source | `/home/tester/hsm/potions/fx/eurusd_1m.csv` |
| Bar window | `2015-01-01T22:00:00-05:00` to `2026-03-31T00:00:00-04:00` |
| Units | 38815 |
| Trade groups | 8210 |
| Winning units | 12341 |
| Losing units | 26465 |
| Net points | -8.13 |
| Point value | $50000.00 |
| Net dollars | $-435,438.75 |
| Close MTM DD | $-436,602.50 |
| Intrabar stress MTM DD | $-436,665.50 |
| Max open units | 5 |
| Net / intrabar stress DD | -1.00 |

Notes: Engine + PaperBroker intraday_st_dca. London→NY session. exit_mode=close. Each unit=0.5 lot (PV=$50k). ATR ST 14×3. add_qty=1 max_adds=5. slippage=1 tick; fee=$0.75/unit.
