# NQ Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/nq_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/nq_monthly_overlap_daily_st_retest5/bars/NQ_4H.csv` |
| Bar window | `2010-06-06T16:00:00-04:00` to `2026-03-08T16:00:00-04:00` |
| Units | 277 |
| Trade groups | 73 |
| Winning units | 124 |
| Losing units | 153 |
| Net points | 27498.78 |
| Point value | $20.00 |
| Net dollars | $549,560.15 |
| Close MTM DD | $-118,019.57 |
| Intrabar stress MTM DD | $-127,454.57 |
| Max open units | 12 |
| Net / intrabar stress DD | 4.31 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
