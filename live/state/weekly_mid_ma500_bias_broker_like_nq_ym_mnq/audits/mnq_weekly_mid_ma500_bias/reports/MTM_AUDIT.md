# MNQ weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/states/mnq_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/states/mnq_weekly_mid_ma500_bias/bars/MNQ_15m.csv` |
| Bar window | `2019-05-05T18:15:00-04:00` to `2026-04-23T20:00:00-04:00` |
| Units | 508 |
| Trade groups | 508 |
| Winning units | 98 |
| Losing units | 410 |
| Net points | 713.00 |
| Point value | $2.00 |
| Net dollars | $664.00 |
| Close MTM DD | $-4,930.75 |
| Intrabar stress MTM DD | $-4,931.75 |
| Max open units | 1 |
| Net / intrabar stress DD | 0.13 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 6 trades/week. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
