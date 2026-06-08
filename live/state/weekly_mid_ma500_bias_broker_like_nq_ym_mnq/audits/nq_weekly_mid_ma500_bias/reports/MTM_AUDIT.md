# NQ weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/states/nq_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/states/nq_weekly_mid_ma500_bias/bars/NQ_15m.csv` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-03-08T20:00:00-04:00` |
| Units | 835 |
| Trade groups | 835 |
| Winning units | 240 |
| Losing units | 595 |
| Net points | 988.00 |
| Point value | $20.00 |
| Net dollars | $18,507.50 |
| Close MTM DD | $-44,963.00 |
| Intrabar stress MTM DD | $-44,998.00 |
| Max open units | 1 |
| Net / intrabar stress DD | 0.41 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 6 trades/week. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
