# NQ 3m Supertrend Wick-Retest Target 50 Broker-Like Replay

This is the larger-history `StrategyPlugin` version of the sample-100 prototype.

| Metric | Value |
|---|---:|
| Market | NQ |
| Signal timeframe | 3m |
| Target | 50.0 pts |
| Trades | 10204 |
| Units | 10204 |
| Win rate | 26.4% |
| Net USD | $-107,566.00 |
| Profit factor | 0.92 |
| Closed DD USD | $-112,038.00 |
| Intrabar stress DD USD | $-112,323.00 |
| Max open units | 1 |
| Net / stress | -0.96 |

State root: `live/state/nq_3m_st_wick_retest_target50_broker_like/states/nq_3m_st_wick_retest_target50`

Files:

- [`unit_fills.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/unit_fills.csv)
- [`equity_curve.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/equity_curve.csv)
- [`fills.csv`](states/nq_3m_st_wick_retest_target50/fills.csv)

Broker-like replay through Engine + PaperBroker. 3m Supertrend ATR(14)x2 wick touch, next-bar-open market entry, 1-left/2-right swing confirmation, 50 point fixed target, close-through-ST exit, max 4 trades/day, slippage=1 tick, fee=$1.50/unit.

## Read

The sample-100 result did not survive the full-history broker-like replay. The
larger run is negative with a weak PF, and the modern 2021+ re-run is also
negative: `live/state/nq_3m_st_wick_retest_target50_broker_like_2021/INDEX.md`.
The main drag is the `trend_break_close` bucket; fixed 50-point targets work
when reached, but they are too infrequent to pay for the churn.

Yearly breakdown: [`yearly_breakdown.csv`](yearly_breakdown.csv).
