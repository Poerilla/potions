# OR Profile Engine — XAUUSD_NY

Sessions walked: **5644** (2003-05-06 → 2026-03-31). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 988 | 17.5% | 1276 | 22.6% |
| break_hold_no1r | 3 | 0.1% | 6 | 0.1% |
| break_revert | 103 | 1.8% | 140 | 2.5% |
| clean_break_1r | 0 | 0.0% | 2 | 0.0% |
| double_fail_range | 862 | 15.3% | 536 | 9.5% |
| fakeout_opposite | 231 | 4.1% | 340 | 6.0% |
| no_break_range | 1 | 0.0% | 1 | 0.0% |
| one_r_reversal | 3456 | 61.2% | 3343 | 59.2% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 5643 | 0.801 | [0.790, 0.811] |
| hit2r_given_1r | touch | 4520 | 0.785 | [0.773, 0.797] |
| hit3r_given_2r | touch | 3548 | 0.785 | [0.772, 0.799] |
| reentry_given_break | touch | 5643 | 0.964 | [0.959, 0.969] |
| reentry_given_no1r_break | touch | 1123 | 0.997 | [0.992, 0.999] |
| revert_boundary_given_1r | touch | 4520 | 0.811 | [0.800, 0.822] |
| traverse_opp_given_1r | touch | 4520 | 0.606 | [0.592, 0.620] |
| opp_break_given_1r_revert | touch | 3667 | 0.838 | [0.826, 0.850] |
| opp_break_given_failed_break | touch | 1120 | 0.976 | [0.965, 0.983] |
| opp_hit1r_given_opp_break | touch | 1093 | 0.211 | [0.188, 0.236] |
| opp_hit2r_given_opp_break | touch | 1093 | 0.142 | [0.122, 0.164] |
| hit1r_given_break | close5 | 5643 | 0.836 | [0.827, 0.846] |
| hit2r_given_1r | close5 | 4720 | 0.788 | [0.776, 0.800] |
| hit3r_given_2r | close5 | 3721 | 0.786 | [0.773, 0.799] |
| reentry_given_break | close5 | 5643 | 0.922 | [0.915, 0.929] |
| reentry_given_no1r_break | close5 | 923 | 0.994 | [0.986, 0.997] |
| revert_boundary_given_1r | close5 | 4720 | 0.811 | [0.800, 0.822] |
| traverse_opp_given_1r | close5 | 4720 | 0.611 | [0.597, 0.624] |
| opp_break_given_1r_revert | close5 | 3828 | 0.744 | [0.730, 0.758] |
| opp_break_given_failed_break | close5 | 917 | 0.955 | [0.940, 0.967] |
| opp_hit1r_given_opp_break | close5 | 876 | 0.388 | [0.356, 0.421] |
| opp_hit2r_given_opp_break | close5 | 876 | 0.266 | [0.238, 0.296] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 5205 | 1.0 | 3.0 | 9.0 | 35.0 |
| close5 | or_width_q=q1 | 1205 | 1.0 | 3.0 | 10.0 | 39.0 |
| close5 | or_width_q=q2 | 1177 | 1.0 | 3.0 | 10.0 | 32.4 |
| close5 | or_width_q=q3 | 1272 | 1.0 | 3.0 | 9.0 | 35.0 |
| close5 | or_width_q=q4 | 1506 | 1.0 | 3.0 | 9.0 | 33.0 |
| close5 | failed_break_no1r | 917 | 1.0 | 2.0 | 3.0 | 7.0 |
| touch | all | 5440 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q1 | 1259 | 0.0 | 1.0 | 4.0 | 15.2 |
| touch | or_width_q=q2 | 1222 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q3 | 1322 | 0.0 | 1.0 | 3.0 | 12.0 |
| touch | or_width_q=q4 | 1587 | 0.0 | 1.0 | 3.0 | 11.4 |
| touch | failed_break_no1r | 1120 | 0.0 | 1.0 | 1.0 | 4.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 171 | 0.591 | -0.195 | 89% (9 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 172 | 0.605 | -0.181 | 89% (9 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 269 | 0.435 | -0.171 | 90% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 189 | 0.439 | -0.167 | 82% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 199 | 0.452 | -0.158 | 91% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 287 | 0.453 | -0.158 | 82% (11 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=flat | 206 | 0.456 | -0.154 | 100% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=flat | 197 | 0.457 | -0.149 | 100% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=flat | 243 | 0.753 | +0.147 | 100% (11 yrs) |
| opp_hit2r_given_opp_break | close5 | or_width_q=q1|break_tod_bucket=early | 129 | 0.411 | +0.145 | 100% (3 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 251 | 0.753 | +0.142 | 100% (11 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 267 | 0.648 | -0.140 | 85% (13 yrs) |
| opp_break_given_1r_revert | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 217 | 0.604 | -0.140 | 89% (9 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_up_sm | 352 | 0.750 | +0.139 | 93% (14 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4 | 1265 | 0.471 | -0.139 | 100% (23 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=early | 954 | 0.472 | -0.139 | 100% (22 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4 | 1206 | 0.468 | -0.138 | 100% (23 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_up_sm | 343 | 0.743 | +0.138 | 87% (15 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|break_tod_bucket=early | 1119 | 0.470 | -0.136 | 100% (23 yrs) |
| opp_hit1r_given_opp_break | close5 | or_width_q=q1|break_tod_bucket=early | 129 | 0.519 | +0.131 | 100% (3 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 202 | 0.708 | -0.130 | 78% (9 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4|gap_bucket=flat | 149 | 0.711 | -0.127 | 86% (7 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=early | 1079 | 0.737 | +0.126 | 96% (22 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|break_tod_bucket=early | 1112 | 0.729 | +0.123 | 91% (22 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1 | 1122 | 0.729 | +0.123 | 91% (22 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 324 | 0.488 | -0.123 | 87% (15 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|break_tod_bucket=mid | 173 | 0.665 | -0.121 | 100% (6 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 1158 | 0.730 | +0.119 | 96% (22 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 189 | 0.693 | -0.118 | 82% (11 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 199 | 0.694 | -0.117 | 82% (11 yrs) |
| hit1r_given_break | close5 | or_width_q=q1|gap_bucket=gap_dn_lg | 130 | 0.954 | +0.117 | 100% (3 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 267 | 0.494 | -0.116 | 77% (13 yrs) |
| hit1r_given_break | touch | break_tod_bucket=mid | 204 | 0.686 | -0.115 | 100% (7 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 308 | 0.672 | -0.113 | 86% (14 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 249 | 0.498 | -0.113 | 80% (10 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 324 | 0.676 | -0.112 | 93% (15 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 219 | 0.676 | -0.110 | 90% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 308 | 0.497 | -0.109 | 93% (14 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=flat | 206 | 0.680 | -0.109 | 80% (10 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 243 | 0.498 | -0.108 | 83% (12 yrs) |
