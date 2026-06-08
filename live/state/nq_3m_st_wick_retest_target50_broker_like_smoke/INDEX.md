# NQ 3m Supertrend Wick-Retest Target 50 Broker-Like Replay

This is the larger-history `StrategyPlugin` version of the sample-100 prototype.

| Metric | Value |
|---|---:|
| Market | NQ |
| Signal timeframe | 3m |
| Target | 50.0 pts |
| Trades | 61 |
| Units | 61 |
| Win rate | 27.9% |
| Net USD | $603.50 |
| Profit factor | 1.37 |
| Closed DD USD | $-975.50 |
| Intrabar stress DD USD | $-994.00 |
| Max open units | 1 |
| Net / stress | 0.61 |

State root: `live/state/nq_3m_st_wick_retest_target50_broker_like_smoke/states/nq_3m_st_wick_retest_target50`

Files:

- [`unit_fills.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/unit_fills.csv)
- [`equity_curve.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/equity_curve.csv)
- [`fills.csv`](states/nq_3m_st_wick_retest_target50/fills.csv)

Broker-like replay through Engine + PaperBroker. 3m Supertrend ATR(14)x2 wick touch, next-bar-open market entry, 1-left/2-right swing confirmation, 50 point fixed target, close-through-ST exit, max 4 trades/day, slippage=1 tick, fee=$1.50/unit.
