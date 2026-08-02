# OR Profile Engine — NQ

Sessions walked: **3987** (2010-06-07 → 2026-06-16). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 822 | 20.6% | 976 | 24.5% |
| break_hold_no1r | 13 | 0.3% | 38 | 1.0% |
| break_revert | 939 | 23.6% | 1077 | 27.0% |
| clean_break_1r | 102 | 2.6% | 205 | 5.1% |
| double_fail_range | 1176 | 29.5% | 784 | 19.7% |
| fakeout_opposite | 232 | 5.8% | 299 | 7.5% |
| no_break_range | 3 | 0.1% | 11 | 0.3% |
| one_r_reversal | 700 | 17.6% | 597 | 15.0% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 3984 | 0.542 | [0.527, 0.558] |
| hit2r_given_1r | touch | 2161 | 0.497 | [0.476, 0.518] |
| hit3r_given_2r | touch | 1075 | 0.442 | [0.412, 0.472] |
| reentry_given_break | touch | 3984 | 0.893 | [0.883, 0.902] |
| reentry_given_no1r_break | touch | 1823 | 0.993 | [0.988, 0.996] |
| revert_boundary_given_1r | touch | 2161 | 0.447 | [0.426, 0.468] |
| traverse_opp_given_1r | touch | 2161 | 0.203 | [0.187, 0.221] |
| opp_break_given_1r_revert | touch | 966 | 0.539 | [0.508, 0.571] |
| opp_break_given_failed_break | touch | 1810 | 0.778 | [0.758, 0.796] |
| opp_hit1r_given_opp_break | touch | 1408 | 0.165 | [0.146, 0.185] |
| opp_hit2r_given_opp_break | touch | 1408 | 0.080 | [0.067, 0.095] |
| hit1r_given_break | close5 | 3976 | 0.590 | [0.575, 0.605] |
| hit2r_given_1r | close5 | 2346 | 0.498 | [0.478, 0.518] |
| hit3r_given_2r | close5 | 1169 | 0.450 | [0.422, 0.479] |
| reentry_given_break | close5 | 3976 | 0.810 | [0.798, 0.822] |
| reentry_given_no1r_break | close5 | 1630 | 0.977 | [0.968, 0.983] |
| revert_boundary_given_1r | close5 | 2346 | 0.448 | [0.428, 0.468] |
| traverse_opp_given_1r | close5 | 2346 | 0.205 | [0.190, 0.222] |
| opp_break_given_1r_revert | close5 | 1050 | 0.431 | [0.402, 0.462] |
| opp_break_given_failed_break | close5 | 1592 | 0.680 | [0.657, 0.703] |
| opp_hit1r_given_opp_break | close5 | 1083 | 0.276 | [0.250, 0.303] |
| opp_hit2r_given_opp_break | close5 | 1083 | 0.132 | [0.113, 0.153] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 3222 | 1.0 | 2.0 | 8.0 | 22.0 |
| close5 | or_width_q=q1 | 691 | 1.0 | 3.0 | 7.0 | 24.0 |
| close5 | or_width_q=q2 | 690 | 1.0 | 2.0 | 7.0 | 18.0 |
| close5 | or_width_q=q3 | 789 | 1.0 | 3.0 | 8.0 | 22.0 |
| close5 | or_width_q=q4 | 1016 | 1.0 | 2.0 | 8.0 | 21.0 |
| close5 | failed_break_no1r | 1592 | 1.0 | 2.0 | 5.0 | 11.0 |
| touch | all | 3556 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q1 | 742 | 0.0 | 1.0 | 3.0 | 9.0 |
| touch | or_width_q=q2 | 775 | 0.0 | 1.0 | 3.0 | 8.6 |
| touch | or_width_q=q3 | 887 | 0.0 | 1.0 | 3.0 | 10.4 |
| touch | or_width_q=q4 | 1111 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | failed_break_no1r | 1810 | 0.0 | 1.0 | 2.0 | 5.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| opp_break_given_failed_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 100 | 0.400 | -0.280 | 100% (3 yrs) |
| hit1r_given_break | touch | break_tod_bucket=1030_1200 | 102 | 0.294 | -0.248 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 163 | 0.344 | -0.246 | 100% (7 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 115 | 0.661 | +0.213 | 100% (4 yrs) |
| hit2r_given_1r | close5 | break_tod_bucket=1030_1200 | 174 | 0.287 | -0.211 | 100% (13 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 100 | 0.410 | +0.204 | 100% (4 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 100 | 0.650 | +0.202 | 100% (4 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 238 | 0.878 | +0.198 | 100% (13 yrs) |
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 220 | 0.486 | -0.194 | 92% (12 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1 | 264 | 0.864 | +0.183 | 100% (14 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 115 | 0.383 | +0.177 | 100% (4 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 127 | 0.323 | -0.175 | 100% (4 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 190 | 0.668 | +0.170 | 100% (10 yrs) |
| hit1r_given_break | close5 | or_width_q=q2|gap_bucket=gap_up_lg | 163 | 0.755 | +0.165 | 100% (9 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|gap_bucket=gap_up_sm | 99 | 0.939 | +0.162 | 100% (3 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 403 | 0.432 | -0.158 | 100% (16 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 140 | 0.343 | -0.155 | 100% (5 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 109 | 0.651 | +0.154 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 169 | 0.645 | +0.147 | 88% (8 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 112 | 0.643 | +0.145 | 100% (3 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 303 | 0.921 | +0.143 | 93% (14 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1 | 306 | 0.918 | +0.140 | 93% (14 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4 | 627 | 0.367 | -0.132 | 100% (16 yrs) |
| hit2r_given_1r | touch | or_width_q=q4 | 573 | 0.366 | -0.131 | 100% (16 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1 | 567 | 0.579 | +0.131 | 100% (14 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 160 | 0.719 | +0.129 | 86% (7 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 564 | 0.369 | -0.129 | 100% (16 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 537 | 0.624 | +0.126 | 93% (14 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 164 | 0.555 | -0.125 | 75% (8 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 537 | 0.572 | +0.124 | 100% (14 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=flat | 222 | 0.469 | -0.122 | 92% (13 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4 | 230 | 0.330 | -0.119 | 100% (9 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 122 | 0.328 | -0.119 | 100% (5 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 567 | 0.323 | +0.117 | 100% (14 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=flat | 223 | 0.426 | -0.116 | 92% (13 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 269 | 0.706 | +0.116 | 92% (12 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 215 | 0.335 | -0.115 | 89% (9 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 326 | 0.475 | -0.115 | 93% (14 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 560 | 0.384 | -0.114 | 100% (16 yrs) |
| hit1r_given_break | touch | or_width_q=q2|gap_bucket=gap_up_lg | 163 | 0.656 | +0.114 | 89% (9 yrs) |
