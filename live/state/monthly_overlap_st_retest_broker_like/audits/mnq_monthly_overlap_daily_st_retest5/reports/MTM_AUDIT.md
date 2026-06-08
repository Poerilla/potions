# MNQ Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mnq_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mnq_monthly_overlap_daily_st_retest5/bars/MNQ_4H.csv` |
| Bar window | `2019-05-05T16:00:00-04:00` to `2026-04-23T16:00:00-04:00` |
| Units | 119 |
| Trade groups | 31 |
| Winning units | 66 |
| Losing units | 53 |
| Net points | 30162.71 |
| Point value | $2.00 |
| Net dollars | $60,146.92 |
| Close MTM DD | $-19,477.20 |
| Intrabar stress MTM DD | $-20,428.20 |
| Max open units | 12 |
| Net / intrabar stress DD | 2.94 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
