# OR Profile Engine — US30

Sessions walked: **2242** (2016-10-27 → 2025-07-15). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 446 | 19.9% | 540 | 24.1% |
| break_hold_no1r | 9 | 0.4% | 18 | 0.8% |
| break_revert | 583 | 26.0% | 650 | 29.0% |
| clean_break_1r | 44 | 2.0% | 93 | 4.1% |
| double_fail_range | 609 | 27.2% | 405 | 18.1% |
| fakeout_opposite | 111 | 5.0% | 142 | 6.3% |
| no_break_range | 5 | 0.2% | 18 | 0.8% |
| one_r_reversal | 435 | 19.4% | 376 | 16.8% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 2237 | 0.558 | [0.538, 0.579] |
| hit2r_given_1r | touch | 1249 | 0.485 | [0.458, 0.513] |
| hit3r_given_2r | touch | 606 | 0.495 | [0.455, 0.535] |
| reentry_given_break | touch | 2237 | 0.907 | [0.894, 0.918] |
| reentry_given_no1r_break | touch | 988 | 0.991 | [0.983, 0.995] |
| revert_boundary_given_1r | touch | 1249 | 0.496 | [0.469, 0.524] |
| traverse_opp_given_1r | touch | 1249 | 0.223 | [0.200, 0.246] |
| opp_break_given_1r_revert | touch | 620 | 0.535 | [0.496, 0.574] |
| opp_break_given_failed_break | touch | 979 | 0.735 | [0.707, 0.762] |
| opp_hit1r_given_opp_break | touch | 720 | 0.154 | [0.130, 0.182] |
| opp_hit2r_given_opp_break | touch | 720 | 0.072 | [0.056, 0.093] |
| hit1r_given_break | close5 | 2224 | 0.605 | [0.584, 0.625] |
| hit2r_given_1r | close5 | 1345 | 0.495 | [0.469, 0.522] |
| hit3r_given_2r | close5 | 666 | 0.492 | [0.455, 0.530] |
| reentry_given_break | close5 | 2224 | 0.836 | [0.820, 0.851] |
| reentry_given_no1r_break | close5 | 879 | 0.980 | [0.968, 0.987] |
| revert_boundary_given_1r | close5 | 1345 | 0.488 | [0.462, 0.515] |
| traverse_opp_given_1r | close5 | 1345 | 0.222 | [0.200, 0.244] |
| opp_break_given_1r_revert | close5 | 657 | 0.446 | [0.408, 0.484] |
| opp_break_given_failed_break | close5 | 861 | 0.635 | [0.603, 0.667] |
| opp_hit1r_given_opp_break | close5 | 547 | 0.260 | [0.225, 0.298] |
| opp_hit2r_given_opp_break | close5 | 547 | 0.110 | [0.086, 0.139] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 1860 | 1.0 | 3.0 | 8.0 | 26.0 |
| close5 | or_width_q=q1 | 377 | 1.0 | 3.0 | 8.0 | 20.0 |
| close5 | or_width_q=q2 | 441 | 1.0 | 3.0 | 8.0 | 31.0 |
| close5 | or_width_q=q3 | 431 | 1.0 | 3.0 | 9.0 | 31.0 |
| close5 | or_width_q=q4 | 569 | 1.0 | 3.0 | 9.0 | 22.0 |
| close5 | failed_break_no1r | 861 | 1.0 | 2.0 | 5.0 | 13.0 |
| touch | all | 2028 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q1 | 409 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q2 | 480 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q3 | 479 | 0.0 | 1.0 | 3.0 | 12.0 |
| touch | or_width_q=q4 | 612 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | failed_break_no1r | 979 | 0.0 | 1.0 | 2.0 | 6.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=1030_1200 | 101 | 0.317 | -0.288 | 100% (5 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 94 | 0.692 | +0.206 | 100% (4 yrs) |
| hit1r_given_break | touch | break_tod_bucket=1030_1200 | 94 | 0.383 | -0.175 | 100% (5 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=flat | 105 | 0.438 | -0.167 | 80% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q2|gap_bucket=gap_dn_sm | 80 | 0.650 | +0.162 | 100% (3 yrs) |
| hit2r_given_1r | touch | or_width_q=q1 | 291 | 0.646 | +0.161 | 100% (9 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 287 | 0.645 | +0.159 | 100% (9 yrs) |
| hit1r_given_break | close5 | break_tod_bucket=1030_1200 | 295 | 0.448 | -0.157 | 100% (10 yrs) |
| hit1r_given_break | touch | or_width_q=q1|gap_bucket=gap_up_lg | 102 | 0.716 | +0.157 | 100% (5 yrs) |
| opp_break_given_failed_break | close5 | break_tod_bucket=1030_1200 | 160 | 0.481 | -0.154 | 78% (9 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q4|gap_bucket=flat | 59 | 0.491 | -0.144 | 100% (3 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 108 | 0.778 | +0.142 | 100% (4 yrs) |
| opp_break_given_failed_break | close5 | or_width_q=q2|break_tod_bucket=0945_1030 | 152 | 0.776 | +0.141 | 100% (7 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1|break_tod_bucket=0945_1030 | 153 | 0.876 | +0.140 | 83% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 102 | 0.745 | +0.140 | 100% (5 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 76 | 0.355 | -0.140 | 100% (3 yrs) |
| hit2r_given_1r | close5 | break_tod_bucket=1030_1200 | 132 | 0.356 | -0.139 | 71% (7 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 289 | 0.633 | +0.138 | 100% (9 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 53 | 0.358 | -0.137 | 100% (3 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 80 | 0.362 | -0.134 | 75% (4 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1 | 315 | 0.629 | +0.133 | 100% (9 yrs) |
| hit2r_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 73 | 0.616 | +0.131 | 100% (3 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 84 | 0.238 | +0.128 | 100% (4 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q1 | 157 | 0.860 | +0.124 | 83% (6 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1 | 94 | 0.234 | +0.124 | 100% (4 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 80 | 0.362 | -0.123 | 75% (4 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 73 | 0.616 | +0.120 | 100% (3 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|break_tod_bucket=0945_1030 | 399 | 0.724 | +0.119 | 100% (9 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=flat | 107 | 0.439 | -0.119 | 80% (5 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 76 | 0.605 | +0.117 | 100% (4 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 82 | 0.720 | +0.115 | 100% (3 yrs) |
| opp_break_given_failed_break | touch | or_width_q=q4 | 349 | 0.622 | -0.114 | 100% (9 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 142 | 0.718 | +0.114 | 100% (6 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4 | 137 | 0.380 | -0.113 | 100% (7 yrs) |
| hit2r_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 76 | 0.605 | +0.110 | 75% (4 yrs) |
| traverse_opp_given_1r | close5 | break_tod_bucket=1030_1200 | 132 | 0.114 | -0.108 | 86% (7 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=0945_1030 | 129 | 0.388 | -0.105 | 100% (7 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 86 | 0.384 | -0.105 | 80% (5 yrs) |
| hit1r_given_break | close5 | or_width_q=q4 | 666 | 0.500 | -0.105 | 100% (9 yrs) |
| hit1r_given_break | touch | or_width_q=q1|gap_bucket=gap_up_sm | 142 | 0.662 | +0.104 | 100% (6 yrs) |
