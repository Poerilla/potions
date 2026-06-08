# MES Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mes_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mes_monthly_overlap_daily_st_retest5/bars/MES_4H.csv` |
| Bar window | `2019-05-05T16:00:00-04:00` to `2023-08-17T08:00:00-04:00` |
| Units | 94 |
| Trade groups | 24 |
| Winning units | 29 |
| Losing units | 65 |
| Net points | 522.60 |
| Point value | $5.00 |
| Net dollars | $2,471.98 |
| Close MTM DD | $-10,261.55 |
| Intrabar stress MTM DD | $-10,344.05 |
| Max open units | 8 |
| Net / intrabar stress DD | 0.24 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
