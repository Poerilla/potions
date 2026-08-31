# OR Profile Engine — USDJPY_NY

Sessions walked: **5940** (2003-05-06 → 2026-03-31). R = 09:30–09:45 NY OR width; triggers profiled: touch (1m pierce, matches v2b stop fills) and close5 (5m close outside OR).

## Terminal day-label distribution

| Label | touch N | touch % | close5 N | close5 % |
|---|---:|---:|---:|---:|
| break_extend_2r | 1219 | 20.5% | 1558 | 26.2% |
| break_hold_no1r | 2 | 0.0% | 3 | 0.1% |
| break_revert | 171 | 2.9% | 223 | 3.8% |
| clean_break_1r | 7 | 0.1% | 17 | 0.3% |
| double_fail_range | 990 | 16.7% | 579 | 9.7% |
| fakeout_opposite | 281 | 4.7% | 443 | 7.5% |
| no_break_range | 1 | 0.0% | 2 | 0.0% |
| one_r_reversal | 3269 | 55.0% | 3115 | 52.4% |

## Headline chains (condition = all)

| Table | Trigger | N | p | Wilson 95% CI |
|---|---|---:|---:|---|
| hit1r_given_break | touch | 5939 | 0.777 | [0.767, 0.788] |
| hit2r_given_1r | touch | 4617 | 0.757 | [0.745, 0.769] |
| hit3r_given_2r | touch | 3496 | 0.749 | [0.735, 0.763] |
| reentry_given_break | touch | 5939 | 0.950 | [0.944, 0.955] |
| reentry_given_no1r_break | touch | 1322 | 0.999 | [0.995, 1.000] |
| revert_boundary_given_1r | touch | 4617 | 0.750 | [0.737, 0.762] |
| traverse_opp_given_1r | touch | 4617 | 0.545 | [0.530, 0.559] |
| opp_break_given_1r_revert | touch | 3463 | 0.809 | [0.795, 0.822] |
| opp_break_given_failed_break | touch | 1320 | 0.963 | [0.951, 0.972] |
| opp_hit1r_given_opp_break | touch | 1271 | 0.221 | [0.199, 0.245] |
| opp_hit2r_given_opp_break | touch | 1271 | 0.142 | [0.124, 0.163] |
| hit1r_given_break | close5 | 5938 | 0.815 | [0.805, 0.825] |
| hit2r_given_1r | close5 | 4839 | 0.763 | [0.751, 0.775] |
| hit3r_given_2r | close5 | 3694 | 0.750 | [0.735, 0.763] |
| reentry_given_break | close5 | 5938 | 0.897 | [0.889, 0.904] |
| reentry_given_no1r_break | close5 | 1099 | 0.997 | [0.992, 0.999] |
| revert_boundary_given_1r | close5 | 4839 | 0.751 | [0.739, 0.763] |
| traverse_opp_given_1r | close5 | 4839 | 0.542 | [0.528, 0.556] |
| opp_break_given_1r_revert | close5 | 3634 | 0.698 | [0.682, 0.712] |
| opp_break_given_failed_break | close5 | 1096 | 0.932 | [0.916, 0.946] |
| opp_hit1r_given_opp_break | close5 | 1022 | 0.433 | [0.403, 0.464] |
| opp_hit2r_given_opp_break | close5 | 1022 | 0.277 | [0.250, 0.305] |

## Empirical failed-break cutoff (5m candles to re-entry)

| Trigger | Condition | N | p25 | median | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|
| close5 | all | 5325 | 1.0 | 3.0 | 9.0 | 33.0 |
| close5 | or_width_q=q1 | 1376 | 1.0 | 3.0 | 10.0 | 40.0 |
| close5 | or_width_q=q2 | 1238 | 1.0 | 3.0 | 8.0 | 29.0 |
| close5 | or_width_q=q3 | 1298 | 1.0 | 3.0 | 8.8 | 32.0 |
| close5 | or_width_q=q4 | 1366 | 1.0 | 3.0 | 10.0 | 35.0 |
| close5 | failed_break_no1r | 1096 | 1.0 | 2.0 | 3.0 | 7.0 |
| touch | all | 5639 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | or_width_q=q1 | 1457 | 0.0 | 1.0 | 4.0 | 17.4 |
| touch | or_width_q=q2 | 1319 | 0.0 | 1.0 | 3.0 | 11.0 |
| touch | or_width_q=q3 | 1371 | 0.0 | 1.0 | 3.0 | 10.0 |
| touch | or_width_q=q4 | 1442 | 0.0 | 1.0 | 3.0 | 13.0 |
| touch | failed_break_no1r | 1320 | 0.0 | 1.0 | 2.0 | 4.0 |

## Stable conditioned edges (sign holds in >=70% of years, N>=30)

| Table | Trigger | Condition | N | p | edge vs all | stability |
|---|---|---|---:|---:|---:|---:|
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 221 | 0.312 | -0.230 | 100% (9 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 201 | 0.313 | -0.228 | 88% (8 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 201 | 0.318 | -0.227 | 100% (7 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 228 | 0.750 | +0.208 | 92% (13 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 199 | 0.342 | -0.203 | 71% (7 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_lg | 210 | 0.348 | -0.194 | 75% (8 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=flat | 145 | 0.352 | -0.193 | 100% (3 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|break_tod_bucket=mid | 201 | 0.562 | -0.189 | 88% (8 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=flat | 220 | 0.727 | +0.182 | 85% (13 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|gap_bucket=flat | 150 | 0.367 | -0.175 | 75% (4 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_dn_sm | 160 | 0.575 | -0.175 | 100% (6 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 237 | 0.371 | -0.174 | 77% (13 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4 | 1063 | 0.372 | -0.172 | 100% (24 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4 | 1114 | 0.372 | -0.169 | 100% (24 yrs) |
| hit3r_given_2r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 181 | 0.586 | -0.164 | 75% (8 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 162 | 0.586 | -0.163 | 100% (6 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q4|break_tod_bucket=early | 981 | 0.383 | -0.162 | 100% (24 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q4|gap_bucket=gap_up_sm | 221 | 0.597 | -0.154 | 89% (9 yrs) |
| revert_boundary_given_1r | close5 | or_width_q=q1|gap_bucket=flat | 228 | 0.903 | +0.152 | 100% (13 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_dn_lg | 208 | 0.692 | +0.150 | 90% (10 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4|gap_bucket=gap_up_sm | 123 | 0.658 | -0.150 | 75% (4 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_dn_lg | 202 | 0.693 | +0.148 | 78% (9 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|gap_bucket=gap_dn_sm | 302 | 0.692 | +0.147 | 93% (15 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 174 | 0.603 | -0.146 | 71% (7 yrs) |
| hit2r_given_1r | close5 | or_width_q=q4|gap_bucket=gap_dn_lg | 293 | 0.618 | -0.146 | 86% (14 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q4|break_tod_bucket=early | 883 | 0.396 | -0.145 | 91% (23 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q1|gap_bucket=flat | 220 | 0.895 | +0.145 | 100% (13 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|gap_bucket=gap_dn_sm | 310 | 0.687 | +0.145 | 87% (15 yrs) |
| hit3r_given_2r | touch | or_width_q=q1|gap_bucket=gap_dn_lg | 169 | 0.893 | +0.144 | 71% (7 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1|break_tod_bucket=early | 1313 | 0.685 | +0.143 | 96% (23 yrs) |
| hit1r_given_break | close5 | or_width_q=q4|break_tod_bucket=mid | 299 | 0.672 | -0.143 | 88% (17 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_lg | 199 | 0.608 | -0.142 | 71% (7 yrs) |
| hit1r_given_break | touch | break_tod_bucket=mid | 187 | 0.636 | -0.141 | 89% (9 yrs) |
| opp_hit1r_given_opp_break | close5 | or_width_q=q1|break_tod_bucket=early | 143 | 0.573 | +0.140 | 75% (4 yrs) |
| opp_break_given_1r_revert | touch | or_width_q=q4|gap_bucket=gap_dn_sm | 148 | 0.669 | -0.140 | 75% (4 yrs) |
| traverse_opp_given_1r | close5 | or_width_q=q1 | 1379 | 0.682 | +0.140 | 96% (24 yrs) |
| hit3r_given_2r | touch | or_width_q=q4|break_tod_bucket=early | 656 | 0.610 | -0.140 | 100% (22 yrs) |
| revert_boundary_given_1r | touch | or_width_q=q4|gap_bucket=gap_up_sm | 201 | 0.612 | -0.138 | 100% (7 yrs) |
| hit2r_given_1r | touch | or_width_q=q4|gap_bucket=gap_dn_lg | 281 | 0.619 | -0.138 | 80% (15 yrs) |
| traverse_opp_given_1r | touch | or_width_q=q1|break_tod_bucket=early | 1322 | 0.682 | +0.137 | 96% (24 yrs) |
