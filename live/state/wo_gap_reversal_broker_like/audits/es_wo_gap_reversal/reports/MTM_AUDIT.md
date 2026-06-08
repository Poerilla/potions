# ES WO Gap Reversal (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/wo_gap_reversal_broker_like/states/es_wo_gap_reversal/fills.csv` |
| Bar source | `/home/tester/hsm/potions/es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-04-24T17:00:00-04:00` |
| Units | 902 |
| Trade groups | 451 |
| Winning units | 444 |
| Losing units | 454 |
| Net points | 2440.00 |
| Point value | $50.00 |
| Net dollars | $120,647.00 |
| Close MTM DD | $-44,937.00 |
| Intrabar stress MTM DD | $-45,687.00 |
| Max open units | 2 |
| Net / intrabar stress DD | 2.64 |

Notes: Broker-like 1h Engine + PaperBroker. W-SUN weekly open gap reversal: 55% gap candle, limit @ WO, 6-bar fill window, swing filter, 2ct +50 / runner 300, SL 50, max 2 trades/week, stop after win. Slippage=1 tick, fee=$1.50/unit.
