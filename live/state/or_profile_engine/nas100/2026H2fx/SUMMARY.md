# OR Profile Engine — NAS100

Sessions walked: **2270** (2016-11-15 → 2025-09-30). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 484 | 21.3% | 565 | 24.9% |
| break_hold_no1r | 8 | 0.4% | 22 | 1.0% |
| break_revert | 556 | 24.5% | 638 | 28.1% |
| clean_break_1r | 61 | 2.7% | 112 | 4.9% |
| double_fail_range | 649 | 28.6% | 439 | 19.3% |
| fakeout_opposite | 123 | 5.4% | 159 | 7.0% |
| no_break_range | 1 | 0.0% | 7 | 0.3% |
| one_r_reversal | 388 | 17.1% | 328 | 14.4% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 2269 | 0.547 | [0.527, 0.568] |
| hit2r_given_1r | touch | 1242 | 0.502 | [0.475, 0.530] |
| hit3r_given_2r | touch | 624 | 0.447 | [0.408, 0.486] |
| reentry_given_break | touch | 2269 | 0.888 | [0.874, 0.900] |
| reentry_given_no1r_break | touch | 1027 | 0.992 | [0.985, 0.996] |
| revert_boundary_given_1r | touch | 1242 | 0.423 | [0.396, 0.451] |
| traverse_opp_given_1r | touch | 1242 | 0.192 | [0.172, 0.215] |
| opp_break_given_1r_revert | touch | 526 | 0.527 | [0.484, 0.569] |
| opp_break_given_failed_break | touch | 1019 | 0.758 | [0.730, 0.783] |
| opp_hit1r_given_opp_break | touch | 772 | 0.159 | [0.135, 0.187] |
| opp_hit2r_given_opp_break | touch | 772 | 0.070 | [0.054, 0.090] |
| hit1r_given_break | close5 | 2263 | 0.589 | [0.568, 0.609] |
| hit2r_given_1r | close5 | 1332 | 0.503 | [0.476, 0.530] |
| hit3r_given_2r | close5 | 670 | 0.461 | [0.424, 0.499] |
| reentry_given_break | close5 | 2263 | 0.811 | [0.795, 0.827] |
| reentry_given_no1r_break | close5 | 931 | 0.976 | [0.965, 0.984] |
| revert_boundary_given_1r | close5 | 1332 | 0.428 | [0.402, 0.455] |
| traverse_opp_given_1r | close5 | 1332 | 0.196 | [0.175, 0.218] |
| opp_break_given_1r_revert | close5 | 570 | 0.430 | [0.390, 0.471] |
| opp_break_given_failed_break | close5 | 909 | 0.658 | [0.626, 0.688] |
| opp_hit1r_given_opp_break | close5 | 598 | 0.266 | [0.232, 0.303] |
| opp_hit2r_given_opp_break | close5 | 598 | 0.124 | [0.100, 0.153] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 1836 | 1.0 | 3.0 | 8.0 | 22.0 |
| close5 | or_width_q=q1 | 378 | 1.0 | 2.0 | 7.0 | 24.0 |
| close5 | or_width_q=q2 | 398 | 1.0 | 3.0 | 8.0 | 18.0 |
| close5 | or_width_q=q3 | 430 | 1.0 | 3.0 | 8.0 | 22.1 |
| close5 | or_width_q=q4 | 587 | 1.0 | 2.0 | 7.5 | 22.0 |
| close5 | failed_break_no1r | 909 | 1.0 | 2.0 | 5.0 | 11.0 |
| touch | all | 2015 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q1 | 409 | 1.0 | 1.0 | 3.0 | 9.2 |
| touch | or_width_q=q2 | 442 | 0.0 | 1.0 | 3.8 | 10.9 |
| touch | or_width_q=q3 | 484 | 1.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q4 | 637 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | failed_break_no1r | 1019 | 0.0 | 1.0 | 2.0 | 6.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 86 | 0.326 | -0.263 | 100% (4 yrs) |
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 120 | 0.458 | -0.200 | 86% (7 yrs) |
| hit1r_given_break | close5 | or_width_q=q2|gap_bucket=gap_up_lg | 102 | 0.774 | +0.186 | 100% (6 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 213 | 0.404 | -0.185 | 100% (9 yrs) |
| hit2r_given_1r | close5 | break_tod_bucket=1030_1200 | 86 | 0.326 | -0.177 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q1|gap_bucket=gap_up_lg | 85 | 0.718 | +0.170 | 75% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q2|gap_bucket=gap_up_lg | 102 | 0.716 | +0.168 | 83% (6 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 93 | 0.645 | +0.142 | 100% (4 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 182 | 0.456 | -0.133 | 86% (7 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 78 | 0.372 | -0.131 | 100% (3 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 137 | 0.788 | +0.131 | 86% (7 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 75 | 0.373 | -0.129 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=flat | 126 | 0.421 | -0.127 | 100% (7 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 90 | 0.378 | -0.125 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=flat | 125 | 0.464 | -0.125 | 86% (7 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 183 | 0.426 | -0.121 | 100% (7 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4 | 141 | 0.340 | -0.121 | 86% (7 yrs) |
| hit3r_given_2r | touch | gap_bucket=gap_up_lg | 134 | 0.567 | +0.120 | 88% (8 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 89 | 0.708 | +0.119 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4 | 365 | 0.386 | -0.117 | 100% (9 yrs) |
| hit2r_given_1r | touch | or_width_q=q4 | 333 | 0.387 | -0.115 | 100% (9 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 331 | 0.390 | -0.113 | 100% (9 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 129 | 0.349 | -0.112 | 83% (6 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 287 | 0.540 | +0.112 | 88% (8 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 83 | 0.615 | +0.112 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 329 | 0.392 | -0.110 | 100% (9 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 287 | 0.610 | +0.107 | 88% (8 yrs) |
| reentry_given_break | close5 | or_width_q=q1|gap_bucket=flat | 97 | 0.917 | +0.106 | 100% (5 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 129 | 0.341 | -0.106 | 86% (7 yrs) |
| hit3r_given_2r | touch | or_width_q=q4 | 129 | 0.341 | -0.106 | 86% (7 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1 | 304 | 0.533 | +0.105 | 88% (8 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 75 | 0.320 | -0.103 | 75% (4 yrs) |
| traverse_opp_given_1r | close5 | break_tod_bucket=1030_1200 | 86 | 0.093 | -0.103 | 100% (4 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 287 | 0.296 | +0.100 | 88% (8 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4 | 365 | 0.332 | -0.096 | 100% (9 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 331 | 0.332 | -0.096 | 100% (9 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q2|gap_bucket=gap_up_sm | 88 | 0.523 | +0.095 | 80% (5 yrs) |
| hit3r_given_2r | close5 | gap_bucket=gap_up_lg | 144 | 0.556 | +0.094 | 75% (8 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 284 | 0.518 | +0.094 | 75% (8 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q1 | 286 | 0.517 | +0.094 | 75% (8 yrs) |
