# Q1 fakeout satellite — loss autopsy & structure what-ifs

Reconstructed 447 of 447 replay trades. Losers 293, winners 154 (trade-level, actual replay PnL).

## Why do we stop out? (after the actual stop, first touch by EOD)

| Cause | N | % |
|---|---:|---:|
| invalidation_continuation | 168 | 57.7 |
| shakeout_then_traverse | 104 | 35.7 |
| chop_neither | 19 | 6.5 |

Minutes from entry to stop: median 6, p25 2, p75 17.

## Trade-structure variants (1 unit, analytic 1m tape, pessimistic same-bar ordering)

| variant | sessions | fills | fill_rate_pct | tp | sl | eod | tp_rate_of_fills_pct | net_usd_1unit | usd_per_fill | usd_per_session | profit_factor | avg_risk_pts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0_asis_1unit_tp_bound | 447 | 447 | 100.0 | 184 | 261 | 2 | 41.2 | 7464.5 | 16.7 | 16.7 | 1.169 | 10.12 |
| V5_asis_entry_deep_stop | 447 | 447 | 100.0 | 280 | 153 | 14 | 62.6 | 3489.5 | 7.81 | 7.81 | 1.043 | 26.78 |
| V3_retest_broken_level | 447 | 406 | 90.8 | 192 | 186 | 28 | 47.3 | 1931.0 | 4.76 | 4.32 | 1.024 | 21.21 |
| V3b_retest_stop_extreme | 447 | 406 | 90.8 | 82 | 320 | 4 | 20.2 | 4816.0 | 11.86 | 10.77 | 1.174 | 4.77 |
| V1_limit_at_failed_extreme | 447 | 361 | 80.8 | 126 | 203 | 32 | 34.9 | -3716.5 | -10.3 | -8.31 | 0.946 | 16.96 |
| V1b_limit_extreme_tp_opp1r | 447 | 361 | 80.8 | 57 | 230 | 74 | 15.8 | -1036.5 | -2.87 | -2.32 | 0.986 | 16.96 |
| V4_swing_5m_london | 447 | 175 | 39.1 | 46 | 116 | 13 | 26.3 | -712.5 | -4.07 | -1.59 | 0.975 | 13.99 |

Variant key: V0 = as traded (single unit, TP at opposite boundary); V5 = same market entry but stop moved to the original-break 1R (directional invalidation); V3/V3b = limit entry on a retest of the broken OR level (stop at invalidation / at failed extreme); V1/V1b = limit entry at the failed extreme itself (old stop becomes entry), stop at invalidation; V4 = limit at the nearest confirmed 5m swing beyond the failed extreme (03:00 NY onward, includes London).