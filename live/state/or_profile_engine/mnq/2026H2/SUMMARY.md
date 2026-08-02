# OR Profile Engine — MNQ

Sessions walked: **1245** (2021-03-04 → 2026-03-03). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 270 | 21.7% | 320 | 25.7% |
| break_hold_no1r | 4 | 0.3% | 10 | 0.8% |
| break_revert | 295 | 23.7% | 352 | 28.3% |
| clean_break_1r | 36 | 2.9% | 65 | 5.2% |
| double_fail_range | 356 | 28.6% | 228 | 18.3% |
| fakeout_opposite | 72 | 5.8% | 82 | 6.6% |
| no_break_range | 0 | 0.0% | 1 | 0.1% |
| one_r_reversal | 212 | 17.0% | 187 | 15.0% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 1245 | 0.563 | [0.535, 0.590] |
| hit2r_given_1r | touch | 701 | 0.486 | [0.450, 0.523] |
| hit3r_given_2r | touch | 341 | 0.431 | [0.380, 0.484] |
| reentry_given_break | touch | 1245 | 0.877 | [0.858, 0.894] |
| reentry_given_no1r_break | touch | 544 | 0.993 | [0.981, 0.997] |
| revert_boundary_given_1r | touch | 701 | 0.436 | [0.400, 0.473] |
| traverse_opp_given_1r | touch | 701 | 0.201 | [0.173, 0.232] |
| opp_break_given_1r_revert | touch | 306 | 0.529 | [0.473, 0.585] |
| opp_break_given_failed_break | touch | 540 | 0.793 | [0.756, 0.825] |
| opp_hit1r_given_opp_break | touch | 428 | 0.168 | [0.136, 0.207] |
| opp_hit2r_given_opp_break | touch | 428 | 0.075 | [0.053, 0.104] |
| hit1r_given_break | close5 | 1244 | 0.624 | [0.597, 0.650] |
| hit2r_given_1r | close5 | 776 | 0.488 | [0.453, 0.523] |
| hit3r_given_2r | close5 | 379 | 0.449 | [0.399, 0.499] |
| reentry_given_break | close5 | 1244 | 0.797 | [0.773, 0.818] |
| reentry_given_no1r_break | close5 | 468 | 0.979 | [0.961, 0.988] |
| revert_boundary_given_1r | close5 | 776 | 0.437 | [0.402, 0.472] |
| traverse_opp_given_1r | close5 | 776 | 0.191 | [0.165, 0.220] |
| opp_break_given_1r_revert | close5 | 339 | 0.416 | [0.365, 0.469] |
| opp_break_given_failed_break | close5 | 458 | 0.677 | [0.633, 0.718] |
| opp_hit1r_given_opp_break | close5 | 310 | 0.265 | [0.218, 0.316] |
| opp_hit2r_given_opp_break | close5 | 310 | 0.126 | [0.093, 0.167] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 991 | 1.0 | 2.0 | 8.0 | 22.0 |
| close5 | or_width_q=q1 | 242 | 1.0 | 2.0 | 7.8 | 25.0 |
| close5 | or_width_q=q2 | 189 | 1.0 | 3.0 | 8.0 | 19.8 |
| close5 | or_width_q=q3 | 221 | 1.0 | 3.0 | 9.0 | 22.0 |
| close5 | or_width_q=q4 | 302 | 1.0 | 2.0 | 6.0 | 21.9 |
| close5 | failed_break_no1r | 458 | 1.0 | 2.0 | 4.0 | 10.0 |
| touch | all | 1092 | 0.0 | 1.0 | 3.0 | 9.0 |
| touch | or_width_q=q1 | 262 | 0.0 | 1.0 | 2.0 | 8.0 |
| touch | or_width_q=q2 | 217 | 0.0 | 1.0 | 3.0 | 9.0 |
| touch | or_width_q=q3 | 245 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q4 | 328 | 0.0 | 1.0 | 3.0 | 9.0 |
| touch | failed_break_no1r | 540 | 0.0 | 1.0 | 2.0 | 4.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 55 | 0.400 | -0.277 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q4 | 160 | 0.281 | -0.205 | 100% (5 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 49 | 0.245 | -0.204 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 158 | 0.285 | -0.202 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4 | 182 | 0.291 | -0.197 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 165 | 0.297 | -0.191 | 100% (5 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 105 | 0.438 | -0.186 | 100% (5 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 80 | 0.850 | +0.173 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 84 | 0.393 | -0.170 | 100% (4 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 92 | 0.457 | -0.167 | 100% (4 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 92 | 0.402 | -0.161 | 100% (4 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1 | 91 | 0.835 | +0.158 | 100% (5 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q1 | 96 | 0.688 | +0.158 | 100% (4 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 95 | 0.684 | +0.155 | 100% (4 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 84 | 0.476 | -0.148 | 100% (4 yrs) |
| reentry_given_break | touch | or_width_q=q3|gap_bucket=gap_up_sm | 83 | 0.735 | -0.142 | 100% (5 yrs) |
| hit1r_given_break | touch | or_width_q=q2|gap_bucket=flat | 54 | 0.704 | +0.141 | 100% (3 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1 | 201 | 0.577 | +0.140 | 100% (5 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 192 | 0.328 | +0.137 | 100% (5 yrs) |
| hit1r_given_break | close5 | or_width_q=q2|gap_bucket=flat | 54 | 0.759 | +0.136 | 100% (3 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 201 | 0.323 | +0.133 | 100% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 192 | 0.568 | +0.131 | 100% (5 yrs) |
| reentry_given_break | close5 | or_width_q=q2|gap_bucket=gap_up_sm | 72 | 0.667 | -0.130 | 75% (4 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1 | 113 | 0.920 | +0.128 | 100% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 42 | 0.309 | -0.127 | 100% (3 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 112 | 0.920 | +0.127 | 100% (5 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 109 | 0.541 | +0.125 | 80% (5 yrs) |
| reentry_given_break | close5 | or_width_q=q1|gap_bucket=flat | 63 | 0.921 | +0.124 | 100% (3 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1 | 179 | 0.324 | +0.123 | 80% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 192 | 0.609 | +0.121 | 80% (5 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 177 | 0.322 | +0.121 | 80% (5 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 177 | 0.605 | +0.118 | 80% (5 yrs) |
| hit1r_given_break | touch | or_width_q=q4 | 359 | 0.446 | -0.117 | 100% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q4 | 358 | 0.508 | -0.115 | 100% (6 yrs) |
| hit1r_given_break | touch | or_width_q=q4|break_tod_bucket=0945_1030 | 351 | 0.450 | -0.113 | 100% (6 yrs) |
| hit2r_given_1r | touch | or_width_q=q1 | 179 | 0.598 | +0.111 | 80% (5 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1 | 76 | 0.237 | +0.111 | 100% (4 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q1 | 116 | 0.526 | +0.110 | 80% (5 yrs) |
| reentry_given_break | close5 | or_width_q=q3|gap_bucket=gap_up_sm | 83 | 0.687 | -0.110 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1 | 201 | 0.597 | +0.109 | 80% (5 yrs) |
