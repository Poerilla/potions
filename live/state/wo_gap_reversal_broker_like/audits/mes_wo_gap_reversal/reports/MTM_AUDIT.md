# MES WO Gap Reversal (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/wo_gap_reversal_broker_like/states/mes_wo_gap_reversal/fills.csv` |
| Bar source | `/home/tester/hsm/potions/mes/mes_1min_raw.csv` |
| Bar window | `2019-05-05T18:00:00-04:00` to `2023-08-17T09:00:00-04:00` |
| Units | 246 |
| Trade groups | 123 |
| Winning units | 111 |
| Losing units | 133 |
| Net points | 1552.75 |
| Point value | $5.00 |
| Net dollars | $7,394.75 |
| Close MTM DD | $-3,302.50 |
| Intrabar stress MTM DD | $-3,315.00 |
| Max open units | 2 |
| Net / intrabar stress DD | 2.23 |

Notes: Broker-like 1h Engine + PaperBroker. W-SUN weekly open gap reversal: 55% gap candle, limit @ WO, 6-bar fill window, swing filter, 2ct +50 / runner 300, SL 50, max 2 trades/week, stop after win. Slippage=1 tick, fee=$1.50/unit.
