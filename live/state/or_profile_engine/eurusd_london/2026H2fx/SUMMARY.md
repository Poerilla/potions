# OR Profile Engine — EURUSD_LONDON

Sessions walked: **5960** (2003-05-06 → 2026-03-31). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 664 | 11.1% | 909 | 15.3% |
| break_hold_no1r | 0 | 0.0% | 1 | 0.0% |
| break_revert | 30 | 0.5% | 40 | 0.7% |
| clean_break_1r | 2 | 0.0% | 2 | 0.0% |
| double_fail_range | 632 | 10.6% | 364 | 6.1% |
| fakeout_opposite | 153 | 2.6% | 285 | 4.8% |
| no_break_range | 1 | 0.0% | 3 | 0.1% |
| one_r_reversal | 4478 | 75.1% | 4356 | 73.1% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 5959 | 0.867 | [0.858, 0.875] |
| hit2r_given_1r | touch | 5166 | 0.839 | [0.829, 0.849] |
| hit3r_given_2r | touch | 4336 | 0.832 | [0.821, 0.843] |
| reentry_given_break | touch | 5959 | 0.974 | [0.970, 0.978] |
| reentry_given_no1r_break | touch | 793 | 1.000 | [0.995, 1.000] |
| revert_boundary_given_1r | touch | 5166 | 0.868 | [0.858, 0.877] |
| traverse_opp_given_1r | touch | 5166 | 0.732 | [0.720, 0.744] |
| opp_break_given_1r_revert | touch | 4482 | 0.915 | [0.907, 0.923] |
| opp_break_given_failed_break | touch | 793 | 0.990 | [0.980, 0.995] |
| opp_hit1r_given_opp_break | touch | 785 | 0.195 | [0.169, 0.224] |
| opp_hit2r_given_opp_break | touch | 785 | 0.138 | [0.115, 0.163] |
| hit1r_given_break | close5 | 5957 | 0.890 | [0.881, 0.897] |
| hit2r_given_1r | close5 | 5300 | 0.847 | [0.837, 0.856] |
| hit3r_given_2r | close5 | 4487 | 0.834 | [0.823, 0.845] |
| reentry_given_break | close5 | 5957 | 0.945 | [0.939, 0.951] |
| reentry_given_no1r_break | close5 | 657 | 0.999 | [0.991, 1.000] |
| revert_boundary_given_1r | close5 | 5300 | 0.868 | [0.859, 0.877] |
| traverse_opp_given_1r | close5 | 5300 | 0.731 | [0.719, 0.742] |
| opp_break_given_1r_revert | close5 | 4601 | 0.840 | [0.829, 0.851] |
| opp_break_given_failed_break | close5 | 656 | 0.989 | [0.978, 0.995] |
| opp_hit1r_given_opp_break | close5 | 649 | 0.439 | [0.401, 0.478] |
| opp_hit2r_given_opp_break | close5 | 649 | 0.310 | [0.275, 0.346] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 5631 | 1.0 | 3.0 | 8.0 | 28.0 |
| close5 | or_width_q=q1 | 1499 | 1.0 | 3.0 | 11.0 | 32.0 |
| close5 | or_width_q=q2 | 1301 | 1.0 | 2.0 | 7.0 | 27.0 |
| close5 | or_width_q=q3 | 1316 | 1.0 | 3.0 | 9.0 | 29.0 |
| close5 | or_width_q=q4 | 1466 | 1.0 | 2.0 | 7.0 | 24.0 |
| close5 | failed_break_no1r | 656 | 1.0 | 1.0 | 3.0 | 6.0 |
| touch | all | 5803 | 0.0 | 1.0 | 2.0 | 11.0 |
| touch | or_width_q=q1 | 1545 | 0.0 | 1.0 | 3.0 | 15.0 |
| touch | or_width_q=q2 | 1341 | 0.0 | 1.0 | 2.0 | 8.0 |
| touch | or_width_q=q3 | 1357 | 0.0 | 1.0 | 3.0 | 12.0 |
| touch | or_width_q=q4 | 1510 | 0.0 | 1.0 | 2.0 | 9.0 |
| touch | failed_break_no1r | 793 | 0.0 | 1.0 | 1.0 | 3.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 219 | 0.530 | -0.202 | 82% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 267 | 0.539 | -0.191 | 100% (12 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 217 | 0.553 | -0.178 | 73% (11 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=mid | 194 | 0.675 | -0.159 | 78% (9 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q3|break_tod_bucket=mid | 217 | 0.576 | -0.154 | 75% (8 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 362 | 0.591 | -0.139 | 94% (18 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=flat | 120 | 0.700 | -0.139 | 100% (3 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 219 | 0.731 | -0.137 | 82% (11 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q4|break_tod_bucket=mid | 209 | 0.703 | -0.137 | 89% (9 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 258 | 0.868 | +0.136 | 93% (15 yrs) |
| hit1r_given_break | touch | or_width_q=q4|gap_bucket=gap_up_sm | 265 | 0.732 | -0.135 | 77% (13 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 346 | 0.598 | -0.134 | 94% (17 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 264 | 0.864 | +0.133 | 94% (16 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 167 | 0.862 | +0.132 | 100% (6 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 265 | 0.762 | -0.127 | 85% (13 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_lg | 398 | 0.854 | +0.122 | 89% (18 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4 | 1288 | 0.609 | -0.122 | 92% (24 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=mid | 347 | 0.769 | -0.120 | 88% (16 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 267 | 0.727 | -0.120 | 92% (12 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4 | 1244 | 0.616 | -0.116 | 100% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_lg | 410 | 0.844 | +0.113 | 89% (18 yrs) |
| traverse_opp_given_1r | close5 | break_tod_bucket=mid | 759 | 0.618 | -0.113 | 88% (24 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 290 | 0.721 | -0.112 | 80% (15 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 202 | 0.738 | -0.109 | 75% (8 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=flat | 169 | 0.840 | +0.108 | 100% (8 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|break_tod_bucket=early | 1458 | 0.840 | +0.108 | 100% (24 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 278 | 0.727 | -0.107 | 86% (14 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_dn_sm | 261 | 0.839 | +0.107 | 100% (15 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1 | 1466 | 0.839 | +0.107 | 100% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=early | 1388 | 0.837 | +0.107 | 100% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 262 | 0.836 | +0.105 | 100% (15 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|break_tod_bucket=early | 1154 | 0.627 | -0.104 | 96% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 1497 | 0.835 | +0.104 | 100% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 382 | 0.631 | -0.100 | 76% (17 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 259 | 0.734 | -0.099 | 77% (13 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 303 | 0.736 | -0.098 | 71% (14 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 365 | 0.636 | -0.096 | 82% (17 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 149 | 0.738 | -0.096 | 80% (5 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 346 | 0.775 | -0.093 | 88% (17 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=early | 977 | 0.640 | -0.091 | 91% (23 yrs) |
