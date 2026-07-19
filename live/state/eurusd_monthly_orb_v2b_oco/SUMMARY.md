# EURUSD monthly ORB — v2b OCO S_1_1_2 (daily-close SL)

OR = first 3 daily sessions. OCO stop @ ORH/ORL. Max 2 trades/month.
Structure **1/1/2** (4 units): 25% @ TP1=**1R**, 25% @ TP2=**2R**, 50% runner.
After TP1 → stop to **BE**. SL: wicks allowed; exit only if daily **close** beyond SL.
Flatten month-end. Unit = 1 lot (PV $100k), fee $7.

| Metric | Value |
|---|---:|
| Net | $99,693 |
| Closed DD | $-120,605 |
| Net/DD | 0.83 |
| Trades (unit exits) | 1278 |
| Units | 1704 |
| WR | 45.3% |
| Months traded | 274 |

Exit reasons: `{'tp:tp1': 217, 'stop_close:runner': 216, 'month_end:runner': 208, 'stop_close:tp2': 208, 'month_end:tp2': 131, 'stop_close:tp1': 131, 'tp:tp2': 85, 'month_end:tp1': 76, 'month_roll:tp1': 2, 'month_roll:tp2': 2, 'month_roll:runner': 2}`

Compare prior monthly ORB limit-retest scaleout3 (~+$22k / 0.45 Net/Stress broker).

CSV: `leaderboard.csv`, `trades_eurusd_monthly_orb_v2b_s112_close_sl.csv`
