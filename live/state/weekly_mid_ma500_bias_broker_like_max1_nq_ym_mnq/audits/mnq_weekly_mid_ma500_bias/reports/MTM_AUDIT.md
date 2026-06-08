# MNQ weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/mnq_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/mnq_weekly_mid_ma500_bias/bars/MNQ_15m.csv` |
| Bar window | `2019-05-05T18:15:00-04:00` to `2026-04-23T20:00:00-04:00` |
| Units | 232 |
| Trade groups | 232 |
| Winning units | 38 |
| Losing units | 194 |
| Net points | -1226.50 |
| Point value | $2.00 |
| Net dollars | $-2,801.00 |
| Close MTM DD | $-7,075.25 |
| Intrabar stress MTM DD | $-7,097.75 |
| Max open units | 1 |
| Net / intrabar stress DD | -0.39 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 1 trades/week, stop after first weekly win=False. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
