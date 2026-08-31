# OR Profile Engine — EURUSD_NY

Sessions walked: **5952** (2003-05-06 → 2026-03-31). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 1284 | 21.6% | 1655 | 27.8% |
| break_hold_no1r | 3 | 0.1% | 3 | 0.1% |
| break_revert | 209 | 3.5% | 266 | 4.5% |
| clean_break_1r | 5 | 0.1% | 16 | 0.3% |
| double_fail_range | 994 | 16.7% | 605 | 10.2% |
| fakeout_opposite | 337 | 5.7% | 418 | 7.0% |
| no_break_range | 0 | 0.0% | 4 | 0.1% |
| one_r_reversal | 3120 | 52.4% | 2985 | 50.2% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 5952 | 0.769 | [0.758, 0.779] |
| hit2r_given_1r | touch | 4575 | 0.747 | [0.735, 0.760] |
| hit3r_given_2r | touch | 3419 | 0.744 | [0.729, 0.758] |
| reentry_given_break | touch | 5952 | 0.948 | [0.942, 0.953] |
| reentry_given_no1r_break | touch | 1377 | 0.998 | [0.994, 0.999] |
| revert_boundary_given_1r | touch | 4575 | 0.737 | [0.724, 0.749] |
| traverse_opp_given_1r | touch | 4575 | 0.516 | [0.502, 0.531] |
| opp_break_given_1r_revert | touch | 3370 | 0.794 | [0.780, 0.807] |
| opp_break_given_failed_break | touch | 1374 | 0.969 | [0.958, 0.977] |
| opp_hit1r_given_opp_break | touch | 1331 | 0.253 | [0.231, 0.277] |
| opp_hit2r_given_opp_break | touch | 1331 | 0.155 | [0.137, 0.176] |
| hit1r_given_break | close5 | 5948 | 0.817 | [0.807, 0.827] |
| hit2r_given_1r | close5 | 4860 | 0.746 | [0.733, 0.758] |
| hit3r_given_2r | close5 | 3624 | 0.748 | [0.734, 0.762] |
| reentry_given_break | close5 | 5948 | 0.893 | [0.884, 0.900] |
| reentry_given_no1r_break | close5 | 1088 | 0.997 | [0.992, 0.999] |
| revert_boundary_given_1r | close5 | 4860 | 0.741 | [0.728, 0.753] |
| traverse_opp_given_1r | close5 | 4860 | 0.518 | [0.504, 0.532] |
| opp_break_given_1r_revert | close5 | 3600 | 0.689 | [0.674, 0.704] |
| opp_break_given_failed_break | close5 | 1085 | 0.943 | [0.927, 0.955] |
| opp_hit1r_given_opp_break | close5 | 1023 | 0.409 | [0.379, 0.439] |
| opp_hit2r_given_opp_break | close5 | 1023 | 0.264 | [0.238, 0.292] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 5309 | 1.0 | 3.0 | 9.0 | 35.0 |
| close5 | or_width_q=q1 | 1436 | 1.0 | 3.0 | 9.0 | 31.0 |
| close5 | or_width_q=q2 | 1250 | 1.0 | 3.0 | 9.0 | 34.0 |
| close5 | or_width_q=q3 | 1278 | 1.0 | 3.0 | 10.0 | 41.0 |
| close5 | or_width_q=q4 | 1298 | 1.0 | 3.0 | 8.0 | 34.0 |
| close5 | failed_break_no1r | 1085 | 1.0 | 2.0 | 3.0 | 6.0 |
| touch | all | 5643 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q1 | 1520 | 0.0 | 1.0 | 3.0 | 14.1 |
| touch | or_width_q=q2 | 1330 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q3 | 1352 | 0.0 | 1.0 | 3.0 | 14.9 |
| touch | or_width_q=q4 | 1391 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | failed_break_no1r | 1374 | 0.0 | 1.0 | 2.0 | 4.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 175 | 0.240 | -0.276 | 100% (6 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 184 | 0.266 | -0.252 | 100% (7 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 229 | 0.266 | -0.250 | 100% (9 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 244 | 0.287 | -0.231 | 100% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 215 | 0.298 | -0.221 | 80% (10 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 215 | 0.526 | -0.220 | 80% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4 | 983 | 0.303 | -0.213 | 100% (21 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 164 | 0.311 | -0.207 | 100% (6 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4 | 1046 | 0.315 | -0.204 | 100% (22 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|break_tod_bucket=early | 905 | 0.313 | -0.204 | 100% (21 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 158 | 0.317 | -0.200 | 100% (5 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=early | 796 | 0.322 | -0.197 | 95% (20 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 257 | 0.556 | -0.191 | 100% (11 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 272 | 0.555 | -0.191 | 100% (13 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=flat | 182 | 0.330 | -0.189 | 71% (7 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 199 | 0.704 | +0.185 | 90% (10 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 143 | 0.559 | -0.184 | 100% (3 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 229 | 0.559 | -0.178 | 78% (9 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 151 | 0.576 | -0.172 | 83% (6 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4 | 590 | 0.622 | -0.172 | 95% (20 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4|break_tod_bucket=early | 559 | 0.624 | -0.170 | 95% (20 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q4 | 642 | 0.520 | -0.169 | 95% (20 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 191 | 0.681 | +0.164 | 88% (8 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 215 | 0.577 | -0.164 | 80% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 257 | 0.354 | -0.162 | 82% (11 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 175 | 0.577 | -0.160 | 83% (6 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q4|break_tod_bucket=early | 499 | 0.533 | -0.156 | 84% (19 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 272 | 0.364 | -0.154 | 77% (13 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=flat | 182 | 0.593 | -0.152 | 86% (7 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 244 | 0.590 | -0.151 | 82% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 416 | 0.668 | +0.150 | 89% (18 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=flat | 164 | 0.598 | -0.150 | 80% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 184 | 0.592 | -0.148 | 86% (7 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 364 | 0.670 | -0.147 | 94% (17 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=early | 1336 | 0.665 | +0.146 | 100% (24 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_dn_sm | 329 | 0.663 | +0.146 | 81% (16 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 1408 | 0.662 | +0.144 | 100% (24 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4 | 1046 | 0.604 | -0.141 | 100% (22 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 365 | 0.627 | -0.141 | 88% (17 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 392 | 0.656 | +0.139 | 88% (17 yrs) |
