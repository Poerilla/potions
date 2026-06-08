# MNQ WO Gap Reversal (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/wo_gap_reversal_broker_like/states/mnq_wo_gap_reversal/fills.csv` |
| Bar source | `/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst` |
| Bar window | `2021-03-04T00:00:00-05:00` to `2026-04-23T20:00:00-04:00` |
| Units | 342 |
| Trade groups | 171 |
| Winning units | 122 |
| Losing units | 220 |
| Net points | 3222.25 |
| Point value | $2.00 |
| Net dollars | $5,931.50 |
| Close MTM DD | $-2,578.00 |
| Intrabar stress MTM DD | $-2,698.00 |
| Max open units | 2 |
| Net / intrabar stress DD | 2.20 |

Notes: Broker-like 1h Engine + PaperBroker. W-SUN weekly open gap reversal: 55% gap candle, limit @ WO, 6-bar fill window, swing filter, 2ct +50 / runner 300, SL 50, max 2 trades/week, stop after win. Slippage=1 tick, fee=$1.50/unit.
