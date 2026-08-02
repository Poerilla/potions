# OR Profile Engine — YM

Sessions walked: **3963** (2010-06-07 → 2026-05-06). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 789 | 19.9% | 958 | 24.2% |
| break_hold_no1r | 15 | 0.4% | 33 | 0.8% |
| break_revert | 944 | 23.8% | 1108 | 28.0% |
| clean_break_1r | 81 | 2.0% | 154 | 3.9% |
| double_fail_range | 1101 | 27.8% | 688 | 17.4% |
| fakeout_opposite | 209 | 5.3% | 283 | 7.1% |
| no_break_range | 8 | 0.2% | 24 | 0.6% |
| one_r_reversal | 816 | 20.6% | 715 | 18.0% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 3955 | 0.560 | [0.544, 0.576] |
| hit2r_given_1r | touch | 2215 | 0.482 | [0.461, 0.502] |
| hit3r_given_2r | touch | 1067 | 0.459 | [0.429, 0.489] |
| reentry_given_break | touch | 3955 | 0.910 | [0.900, 0.918] |
| reentry_given_no1r_break | touch | 1740 | 0.991 | [0.986, 0.995] |
| revert_boundary_given_1r | touch | 2215 | 0.498 | [0.477, 0.519] |
| traverse_opp_given_1r | touch | 2215 | 0.242 | [0.225, 0.260] |
| opp_break_given_1r_revert | touch | 1103 | 0.563 | [0.534, 0.592] |
| opp_break_given_failed_break | touch | 1725 | 0.759 | [0.739, 0.779] |
| opp_hit1r_given_opp_break | touch | 1310 | 0.160 | [0.141, 0.180] |
| opp_hit2r_given_opp_break | touch | 1310 | 0.077 | [0.064, 0.093] |
| hit1r_given_break | close5 | 3939 | 0.609 | [0.593, 0.624] |
| hit2r_given_1r | close5 | 2397 | 0.492 | [0.472, 0.512] |
| hit3r_given_2r | close5 | 1180 | 0.457 | [0.428, 0.485] |
| reentry_given_break | close5 | 3939 | 0.839 | [0.827, 0.850] |
| reentry_given_no1r_break | close5 | 1542 | 0.979 | [0.970, 0.985] |
| revert_boundary_given_1r | close5 | 2397 | 0.491 | [0.471, 0.511] |
| traverse_opp_given_1r | close5 | 2397 | 0.237 | [0.220, 0.254] |
| opp_break_given_1r_revert | close5 | 1178 | 0.466 | [0.438, 0.495] |
| opp_break_given_failed_break | close5 | 1509 | 0.643 | [0.619, 0.667] |
| opp_hit1r_given_opp_break | close5 | 971 | 0.291 | [0.264, 0.321] |
| opp_hit2r_given_opp_break | close5 | 971 | 0.123 | [0.103, 0.145] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 3303 | 1.0 | 3.0 | 8.0 | 23.0 |
| close5 | or_width_q=q1 | 742 | 1.0 | 3.0 | 7.0 | 24.0 |
| close5 | or_width_q=q2 | 755 | 1.0 | 3.0 | 8.0 | 22.6 |
| close5 | or_width_q=q3 | 804 | 1.0 | 3.0 | 8.0 | 27.0 |
| close5 | or_width_q=q4 | 964 | 1.0 | 3.0 | 8.0 | 21.0 |
| close5 | failed_break_no1r | 1509 | 1.0 | 2.0 | 5.0 | 11.0 |
| touch | all | 3598 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q1 | 798 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q2 | 824 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q3 | 893 | 0.0 | 1.0 | 3.0 | 9.0 |
| touch | or_width_q=q4 | 1040 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | failed_break_no1r | 1725 | 0.0 | 1.0 | 2.0 | 6.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| hit1r_given_break | close5 | break_tod_bucket=1200_eod | 108 | 0.222 | -0.386 | 100% (3 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 106 | 0.387 | -0.257 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 171 | 0.368 | -0.240 | 100% (10 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 208 | 0.861 | +0.217 | 100% (9 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 176 | 0.665 | +0.183 | 90% (10 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1 | 243 | 0.823 | +0.180 | 90% (10 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 289 | 0.934 | +0.175 | 100% (12 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1 | 295 | 0.929 | +0.169 | 100% (12 yrs) |
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 264 | 0.477 | -0.166 | 86% (14 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q4|gap_bucket=flat | 116 | 0.595 | -0.165 | 75% (4 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 189 | 0.656 | +0.164 | 91% (11 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|gap_bucket=gap_up_sm | 91 | 0.923 | +0.164 | 100% (3 yrs) |
| hit1r_given_break | touch | break_tod_bucket=1030_1200 | 141 | 0.397 | -0.163 | 100% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 123 | 0.333 | -0.158 | 83% (6 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 154 | 0.604 | -0.155 | 100% (5 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=flat | 200 | 0.455 | -0.153 | 100% (11 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q4|gap_bucket=flat | 107 | 0.495 | -0.148 | 75% (4 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 504 | 0.466 | -0.142 | 100% (16 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 109 | 0.624 | +0.142 | 80% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 120 | 0.633 | +0.141 | 100% (5 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 135 | 0.341 | -0.141 | 83% (6 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 123 | 0.098 | -0.139 | 83% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 190 | 0.747 | +0.139 | 100% (9 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=flat | 203 | 0.424 | -0.136 | 91% (11 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4 | 228 | 0.329 | -0.128 | 100% (11 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1 | 200 | 0.250 | +0.127 | 78% (9 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 123 | 0.366 | -0.126 | 83% (6 yrs) |
| hit2r_given_1r | close5 | break_tod_bucket=1030_1200 | 235 | 0.366 | -0.126 | 73% (15 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 783 | 0.734 | +0.126 | 88% (16 yrs) |
| hit1r_given_break | touch | or_width_q=q1|gap_bucket=gap_dn_sm | 191 | 0.686 | +0.126 | 100% (9 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 563 | 0.608 | +0.126 | 94% (16 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q4 | 605 | 0.635 | -0.125 | 100% (16 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 141 | 0.369 | -0.123 | 75% (8 yrs) |
| hit1r_given_break | close5 | or_width_q=q2|break_tod_bucket=1030_1200 | 107 | 0.486 | -0.122 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q1 | 571 | 0.604 | +0.122 | 94% (16 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 289 | 0.488 | -0.121 | 80% (10 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 179 | 0.240 | +0.118 | 78% (9 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q3|gap_bucket=gap_up_lg | 104 | 0.375 | -0.116 | 100% (3 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 575 | 0.607 | +0.116 | 87% (15 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 207 | 0.343 | -0.114 | 100% (10 yrs) |
