# OR Profile Engine — MYM

Sessions walked: **1698** (2019-05-06 → 2026-03-06). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 346 | 20.4% | 424 | 25.0% |
| break_hold_no1r | 9 | 0.5% | 18 | 1.1% |
| break_revert | 433 | 25.5% | 495 | 29.2% |
| clean_break_1r | 37 | 2.2% | 70 | 4.1% |
| double_fail_range | 488 | 28.7% | 315 | 18.6% |
| fakeout_opposite | 77 | 4.5% | 103 | 6.1% |
| no_break_range | 2 | 0.1% | 11 | 0.6% |
| one_r_reversal | 306 | 18.0% | 262 | 15.4% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 1696 | 0.543 | [0.519, 0.567] |
| hit2r_given_1r | touch | 921 | 0.489 | [0.456, 0.521] |
| hit3r_given_2r | touch | 450 | 0.438 | [0.393, 0.484] |
| reentry_given_break | touch | 1696 | 0.904 | [0.890, 0.918] |
| reentry_given_no1r_break | touch | 775 | 0.988 | [0.978, 0.994] |
| revert_boundary_given_1r | touch | 921 | 0.468 | [0.436, 0.500] |
| traverse_opp_given_1r | touch | 921 | 0.210 | [0.184, 0.237] |
| opp_break_given_1r_revert | touch | 431 | 0.527 | [0.479, 0.573] |
| opp_break_given_failed_break | touch | 766 | 0.738 | [0.705, 0.767] |
| opp_hit1r_given_opp_break | touch | 565 | 0.136 | [0.110, 0.167] |
| opp_hit2r_given_opp_break | touch | 565 | 0.062 | [0.045, 0.085] |
| hit1r_given_break | close5 | 1687 | 0.596 | [0.573, 0.620] |
| hit2r_given_1r | close5 | 1006 | 0.497 | [0.466, 0.528] |
| hit3r_given_2r | close5 | 500 | 0.440 | [0.397, 0.484] |
| reentry_given_break | close5 | 1687 | 0.832 | [0.813, 0.849] |
| reentry_given_no1r_break | close5 | 681 | 0.974 | [0.959, 0.983] |
| revert_boundary_given_1r | close5 | 1006 | 0.462 | [0.432, 0.493] |
| traverse_opp_given_1r | close5 | 1006 | 0.206 | [0.182, 0.232] |
| opp_break_given_1r_revert | close5 | 465 | 0.428 | [0.384, 0.473] |
| opp_break_given_failed_break | close5 | 663 | 0.630 | [0.593, 0.666] |
| opp_hit1r_given_opp_break | close5 | 418 | 0.246 | [0.207, 0.290] |
| opp_hit2r_given_opp_break | close5 | 418 | 0.093 | [0.069, 0.125] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 1403 | 1.0 | 3.0 | 8.0 | 27.0 |
| close5 | or_width_q=q1 | 283 | 1.0 | 2.0 | 7.0 | 20.8 |
| close5 | or_width_q=q2 | 311 | 1.0 | 3.0 | 8.0 | 29.0 |
| close5 | or_width_q=q3 | 337 | 1.0 | 3.0 | 9.0 | 32.4 |
| close5 | or_width_q=q4 | 428 | 1.0 | 2.0 | 8.2 | 23.0 |
| close5 | failed_break_no1r | 663 | 1.0 | 2.0 | 6.0 | 12.0 |
| touch | all | 1534 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q1 | 310 | 0.0 | 1.0 | 3.0 | 9.1 |
| touch | or_width_q=q2 | 341 | 0.0 | 1.0 | 3.0 | 14.0 |
| touch | or_width_q=q3 | 369 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q4 | 467 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | failed_break_no1r | 766 | 0.0 | 1.0 | 2.0 | 6.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 71 | 0.268 | -0.329 | 100% (4 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 78 | 0.859 | +0.229 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 71 | 0.704 | +0.216 | 100% (3 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 73 | 0.699 | +0.202 | 100% (3 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 113 | 0.929 | +0.192 | 100% (6 yrs) |
| hit1r_given_break | touch | break_tod_bucket=1030_1200 | 71 | 0.352 | -0.191 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 221 | 0.674 | +0.186 | 100% (7 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1 | 115 | 0.922 | +0.184 | 100% (6 yrs) |
| hit2r_given_1r | touch | or_width_q=q1 | 226 | 0.673 | +0.184 | 100% (7 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4 | 93 | 0.258 | -0.182 | 100% (5 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1 | 94 | 0.808 | +0.178 | 100% (3 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 89 | 0.270 | -0.170 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 227 | 0.665 | +0.168 | 100% (7 yrs) |
| hit3r_given_2r | touch | or_width_q=q4 | 81 | 0.272 | -0.166 | 100% (3 yrs) |
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 116 | 0.466 | -0.165 | 100% (6 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1 | 247 | 0.660 | +0.163 | 100% (7 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 80 | 0.275 | -0.163 | 100% (3 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 211 | 0.441 | -0.156 | 100% (7 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q2|gap_bucket=gap_up_sm | 63 | 0.619 | +0.151 | 75% (4 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q2|gap_bucket=gap_dn_sm | 60 | 0.617 | +0.149 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 305 | 0.744 | +0.148 | 100% (7 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 70 | 0.486 | -0.145 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 135 | 0.452 | -0.144 | 80% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q2|gap_bucket=gap_up_sm | 68 | 0.603 | +0.141 | 75% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q1|gap_bucket=gap_up_sm | 104 | 0.683 | +0.140 | 83% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 121 | 0.463 | -0.134 | 80% (5 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 136 | 0.412 | -0.131 | 80% (5 yrs) |
| traverse_opp_given_1r | close5 | break_tod_bucket=1030_1200 | 93 | 0.075 | -0.131 | 100% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q4 | 504 | 0.466 | -0.130 | 100% (8 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 104 | 0.413 | -0.130 | 80% (5 yrs) |
| hit1r_given_break | close5 | or_width_q=q1 | 341 | 0.724 | +0.128 | 100% (7 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 65 | 0.723 | +0.127 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q4 | 510 | 0.422 | -0.121 | 100% (8 yrs) |
| hit1r_given_break | touch | or_width_q=q1 | 341 | 0.663 | +0.120 | 86% (7 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4 | 81 | 0.407 | -0.119 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 334 | 0.662 | +0.119 | 86% (7 yrs) |
| revert_boundary_given_1r | close5 | break_tod_bucket=1030_1200 | 93 | 0.344 | -0.118 | 100% (6 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 77 | 0.623 | -0.114 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q4 | 215 | 0.377 | -0.112 | 71% (7 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 103 | 0.485 | -0.111 | 80% (5 yrs) |
