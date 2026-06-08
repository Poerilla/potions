# NQ weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/nq_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/nq_weekly_mid_ma500_bias/bars/NQ_15m.csv` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-03-08T20:00:00-04:00` |
| Units | 516 |
| Trade groups | 516 |
| Winning units | 168 |
| Losing units | 348 |
| Net points | -417.75 |
| Point value | $20.00 |
| Net dollars | $-9,129.00 |
| Close MTM DD | $-66,362.00 |
| Intrabar stress MTM DD | $-66,667.00 |
| Max open units | 1 |
| Net / intrabar stress DD | -0.14 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 1 trades/week, stop after first weekly win=False. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
