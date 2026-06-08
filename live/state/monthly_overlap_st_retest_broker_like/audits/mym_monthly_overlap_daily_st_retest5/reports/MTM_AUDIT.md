# MYM Monthly ORB overlap daily-ST retest x5

| Metric | Value |
|---|---:|
| Source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mym_monthly_overlap_daily_st_retest5/fills.csv` |
| Bar source | `/home/tester/hsm/potions/live/state/monthly_overlap_st_retest_broker_like/states/mym_monthly_overlap_daily_st_retest5/bars/MYM_4H.csv` |
| Bar window | `2019-05-05T16:00:00-04:00` to `2026-03-08T16:00:00-04:00` |
| Units | 118 |
| Trade groups | 30 |
| Winning units | 41 |
| Losing units | 77 |
| Net points | 19625.20 |
| Point value | $0.50 |
| Net dollars | $9,635.60 |
| Close MTM DD | $-5,066.60 |
| Intrabar stress MTM DD | $-5,324.60 |
| Max open units | 8 |
| Net / intrabar stress DD | 1.81 |

Notes: Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, confirmed daily Supertrend filter, max two active primary packages, and one 5-contract daily-ST retest limit add per runner. Orders activate only after the confirming 4h bar closes. Realism: slippage=1 tick(s), fee=$1.50/unit.
