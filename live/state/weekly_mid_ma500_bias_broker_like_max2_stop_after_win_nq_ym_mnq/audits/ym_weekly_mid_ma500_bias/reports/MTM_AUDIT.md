# YM weekly 50% + MA500 bias retest (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `live/state/weekly_mid_ma500_bias_broker_like_max2_stop_after_win_nq_ym_mnq/states/ym_weekly_mid_ma500_bias/fills.csv` |
| Bar source | `live/state/weekly_mid_ma500_bias_broker_like_max2_stop_after_win_nq_ym_mnq/states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv` |
| Bar window | `2010-06-06T18:00:00-04:00` to `2026-05-06T20:00:00-04:00` |
| Units | 736 |
| Trade groups | 736 |
| Winning units | 140 |
| Losing units | 596 |
| Net points | 1914.00 |
| Point value | $5.00 |
| Net dollars | $8,466.00 |
| Close MTM DD | $-9,969.00 |
| Intrabar stress MTM DD | $-10,004.00 |
| Max open units | 1 |
| Net / intrabar stress DD | 0.85 |

Notes: Broker-like 15m Engine + PaperBroker replay. Previous-week 50% entry level, bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, target 300.0 pts, stop 50.0 pts, max 2 trades/week, stop after first weekly win=True. Orders activate only after the confirming bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
