# YM weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/ym_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_max1_nq_ym_mnq/states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-05-06T20:00:00-04:00` |
| Units | 505 |
| Trade groups | 505 |
| Winning units | 86 |
| Losing units | 419 |
| Net points | -1467.50 |
| Point value | $5.00 |
| Net dollars | $-8,095.00 |
| Close MTM DD | $-15,510.50 |
| Intrabar stress MTM DD | $-15,600.50 |
| Max open units | 1 |
| Net / intrabar stress DD | -0.52 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 1 trades/week, stop after first weekly win=False. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
