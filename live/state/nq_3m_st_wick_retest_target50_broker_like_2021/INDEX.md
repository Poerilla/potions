# NQ 3m Supertrend Wick-Retest Target 50 Broker-Like Replay

This is the larger-history `StrategyPlugin` version of the sample-100 prototype.

| Metric | Value |
|---|---:|
| Market | NQ |
| Signal timeframe | 3m |
| Target | 50.0 pts |
| Trades | 3397 |
| Units | 3397 |
| Win rate | 30.5% |
| Net USD | $-30,225.50 |
| Profit factor | 0.96 |
| Closed DD USD | $-53,289.50 |
| Intrabar stress DD USD | $-53,574.50 |
| Max open units | 1 |
| Net / stress | -0.56 |

State root: `live/state/nq_3m_st_wick_retest_target50_broker_like_2021/states/nq_3m_st_wick_retest_target50`

Files:

- [`unit_fills.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/unit_fills.csv)
- [`equity_curve.csv`](audits/nq_3m_st_wick_retest_target50/nq_3m_st_wick_retest_target50/equity_curve.csv)
- [`fills.csv`](states/nq_3m_st_wick_retest_target50/fills.csv)

Broker-like replay through Engine + PaperBroker. 3m Supertrend ATR(14)x2 wick touch, next-bar-open market entry, 1-left/2-right swing confirmation, 50 point fixed target, close-through-ST exit, max 4 trades/day, slippage=1 tick, fee=$1.50/unit.

## Read

The 2021+ window improves versus the full archive, but it still does not clear
the broker-like hurdle. 2022 is positive; 2025 is the largest failure cluster.
The rule needs an additional churn filter before it deserves more work as a
deployment candidate.

Yearly breakdown: [`yearly_breakdown.csv`](yearly_breakdown.csv).
