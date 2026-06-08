# ES Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/es_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/es_monthly_overlap_daily_st_retest5/bars/ES_4H.csv` |
| Bar window | `2010-06-06T16:00:00-04:00` to `2026-04-24T16:00:00-04:00` |
| Units | 316 |
| Trade groups | 82 |
| Winning units | 108 |
| Losing units | 208 |
| Net points | 2714.69 |
| Point value | $50.00 |
| Net dollars | $135,260.31 |
| Close MTM DD | $-100,652.97 |
| Intrabar stress MTM DD | $-101,515.47 |
| Max open units | 12 |
| Net / intrabar stress DD | 1.33 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
