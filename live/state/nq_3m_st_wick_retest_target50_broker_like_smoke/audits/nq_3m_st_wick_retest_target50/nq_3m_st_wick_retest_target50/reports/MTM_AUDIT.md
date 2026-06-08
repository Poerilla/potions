# NQ 3m Supertrend Wick-Retest Target 50 (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/nq_3m_st_wick_retest_target50_broker_like_smoke/states/nq_3m_st_wick_retest_target50/fills.csv` |
| Bar source | `/home/tester/hsm/potions/nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst` |
| Bar window | `2010-06-07T09:30:00-04:00` to `2010-07-09T16:00:00-04:00` |
| Units | 61 |
| Trade groups | 61 |
| Winning units | 17 |
| Losing units | 44 |
| Net points | 34.75 |
| Point value | $20.00 |
| Net dollars | $603.50 |
| Close MTM DD | $-975.50 |
| Intrabar stress MTM DD | $-994.00 |
| Max open units | 1 |
| Net / intrabar stress DD | 0.61 |

Notes: Broker-like replay through Engine + PaperBroker. 3m Supertrend ATR(14)x2 wick touch, next-bar-open market entry, 1-left/2-right swing confirmation, 50 point fixed target, close-through-ST exit, max 4 trades/day, slippage=1 tick, fee=$1.50/unit.
