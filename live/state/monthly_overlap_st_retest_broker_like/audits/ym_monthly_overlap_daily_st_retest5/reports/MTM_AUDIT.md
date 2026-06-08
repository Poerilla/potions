# YM Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/ym_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/ym_monthly_overlap_daily_st_retest5/bars/YM_4H.csv` |
| Bar window | `2010-06-06T16:00:00-04:00` to `2026-05-06T16:00:00-04:00` |
| Units | 193 |
| Trade groups | 51 |
| Winning units | 55 |
| Losing units | 138 |
| Net points | 3018.04 |
| Point value | $5.00 |
| Net dollars | $14,800.72 |
| Close MTM DD | $-43,010.47 |
| Intrabar stress MTM DD | $-46,115.47 |
| Max open units | 10 |
| Net / intrabar stress DD | 0.32 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
