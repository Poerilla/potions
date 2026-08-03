# OR Profile -> v2b S_1_1_3 join (2026H2)

Trigger = `touch` (matches v2b stop fills). Fit window = tape start -> 2024-12-31; policies are derived on the fit window only and frozen in `policies.json`.

## NQ

Fit sessions joined: 680 (2021-03-04 -> 2024-12-31), mean net/session $757.19

### v2b expectancy by terminal day label (fit, diagnostic — EOD-knowable)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years |
|---|---|---|---|---|---|---|---|---|---|
| label=double_fail_range | 194 | -1490690.0 | -7683.97 | -7490.0 | 0.149 | 0.121 | -8441.16 | 1.0 | 4 |
| label=one_r_reversal | 125 | -286842.5 | -2294.74 | -3140.0 | 0.376 | 0.554 | -3051.93 | 1.0 | 3 |
| label=fakeout_opposite | 38 | 33545.0 | 882.76 | -235.0 | 0.474 | 1.383 | 125.58 | 0.667 | 3 |
| label=break_revert | 159 | 526425.0 | 3310.85 | 2507.5 | 0.836 | 5.31 | 2553.66 | 1.0 | 3 |
| label=break_hold_no1r | 3 | 13317.5 | 4439.17 | 3435.0 | 1.0 | inf | 3681.98 |  | 0 |
| label=clean_break_1r | 18 | 182075.0 | 10115.28 | 8260.0 | 1.0 | inf | 9358.09 |  | 0 |
| label=break_extend_2r | 143 | 1537057.5 | 10748.65 | 10472.5 | 0.993 | 5255.897 | 9991.47 | 1.0 | 3 |

### v2b expectancy by pre-entry state (fit)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years | knowable |
|---|---|---|---|---|---|---|---|---|---|---|
| or_width_q=q4|gap_bucket=gap_dn_sm | 41 | -98085.0 | -2392.32 | 192.5 | 0.512 | 0.692 | -3149.5 | 1.0 | 2 | 0945 |
| or_width_q=q1|gap_bucket=flat | 46 | -67845.0 | -1474.89 | -2297.5 | 0.435 | 0.579 | -2232.08 | 1.0 | 3 | 0945 |
| or_width_q=q3|gap_bucket=flat | 27 | -29747.5 | -1101.76 | -5120.0 | 0.444 | 0.788 | -1858.95 | 1.0 | 1 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_sm | 34 | -37332.5 | -1098.01 | -292.5 | 0.5 | 0.678 | -1855.2 | 0.5 | 2 | 0945 |
| or_width_q=q4|gap_bucket=gap_up_lg | 26 | -15587.5 | -599.52 | 1506.25 | 0.577 | 0.904 | -1356.71 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=flat | 31 | -15685.0 | -505.97 | 1687.5 | 0.548 | 0.913 | -1263.16 | 1.0 | 2 | 0945 |
| gap_bucket=gap_dn_sm | 142 | -51180.0 | -360.42 | 948.75 | 0.535 | 0.919 | -1117.61 | 0.667 | 3 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_lg | 20 | -5260.0 | -263.0 | 1898.75 | 0.55 | 0.953 | -1020.19 |  | 0 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_sm | 39 | -8980.0 | -230.26 | -620.0 | 0.487 | 0.925 | -987.44 | 0.5 | 2 | 0945 |
| gap_bucket=flat | 139 | -29355.0 | -211.19 | 200.0 | 0.511 | 0.948 | -968.37 | 1.0 | 3 | 0945 |
| or_loc_bucket=mid_third | 152 | 25132.5 | 165.35 | 987.5 | 0.546 | 1.047 | -591.84 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_sm | 40 | 11257.5 | 281.44 | 1277.5 | 0.625 | 1.075 | -475.75 | 0.667 | 3 | 0945 |
| or_loc_bucket=lower_third | 105 | 39260.0 | 373.9 | 1082.5 | 0.562 | 1.09 | -383.28 | 0.667 | 3 | 0945 |
| or_width_q=q4|gap_bucket=gap_up_sm | 58 | 22445.0 | 386.98 | 2758.75 | 0.586 | 1.079 | -370.2 | 0.5 | 2 | 0945 |
| or_width_q=q1 | 193 | 79267.5 | 410.71 | 547.5 | 0.523 | 1.154 | -346.48 | 1.0 | 3 | 0945 |
| or_loc_bucket=upper_third | 175 | 90965.0 | 519.8 | 487.5 | 0.514 | 1.128 | -237.39 | 0.667 | 3 | 0945 |
| or_width_q=q4 | 185 | 113770.0 | 614.97 | 2142.5 | 0.584 | 1.112 | -142.21 | 0.5 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_lg | 25 | 20515.0 | 820.6 | 852.5 | 0.64 | 1.431 | 63.41 | 1.0 | 1 | 0945 |
| or_width_q=q2 | 146 | 126215.0 | 864.49 | 1110.0 | 0.623 | 1.295 | 107.3 | 0.667 | 3 | 0945 |
| gap_bucket=gap_up_sm | 202 | 196677.5 | 973.65 | 1383.75 | 0.579 | 1.277 | 216.46 | 0.667 | 3 | 0945 |
| or_loc_bucket=below_prior | 96 | 98937.5 | 1030.6 | 1605.0 | 0.625 | 1.256 | 273.41 | 0.333 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_lg | 12 | 14417.5 | 1201.46 | 1095.0 | 0.75 | 1.626 | 444.27 |  | 0 | 0945 |
| or_width_q=q3 | 156 | 195635.0 | 1254.07 | 1457.5 | 0.577 | 1.332 | 496.88 | 1.0 | 3 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_sm | 48 | 63630.0 | 1325.62 | 1417.5 | 0.562 | 1.379 | 568.44 | 1.0 | 2 | 0945 |
| gap_bucket=gap_up_lg | 111 | 148390.0 | 1336.85 | 1917.5 | 0.622 | 1.387 | 579.66 | 0.667 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_lg | 27 | 36232.5 | 1341.94 | 1485.0 | 0.556 | 1.454 | 584.76 | 1.0 | 1 | 0945 |
| or_loc_bucket=above_prior | 152 | 260592.5 | 1714.42 | 2270.0 | 0.645 | 1.538 | 957.24 | 1.0 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_sm | 56 | 99345.0 | 1774.02 | 580.0 | 0.554 | 1.93 | 1016.83 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_lg | 25 | 53950.0 | 2158.0 | 1917.5 | 0.72 | 2.069 | 1400.81 | 1.0 | 1 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_lg | 33 | 73795.0 | 2236.21 | 3567.5 | 0.636 | 1.815 | 1479.02 | 0.5 | 2 | 0945 |
| or_width_q=q2|gap_bucket=flat | 35 | 83922.5 | 2397.79 | 1542.5 | 0.629 | 1.953 | 1640.6 | 0.667 | 3 | 0945 |
| gap_bucket=gap_dn_lg | 86 | 250355.0 | 2911.1 | 2323.75 | 0.663 | 1.984 | 2153.92 | 0.667 | 3 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_sm | 28 | 93217.5 | 3329.2 | 4180.0 | 0.679 | 2.19 | 2572.01 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_lg | 29 | 220682.5 | 7609.74 | 8335.0 | 0.724 | 4.055 | 6852.55 | 1.0 | 2 | 0945 |

### Frozen policies

```json
{
  "P1_skip": {
    "rule": "skip session when any cell matches (state knowable at 09:45)",
    "mechanism": "regime_dates restriction",
    "cells": [
      {
        "dim": "gap_bucket",
        "value": "flat",
        "condition": "gap_bucket=flat",
        "n_sessions": 139,
        "total_net": -29355.0,
        "mean_net": -211.19,
        "median_net": 200.0,
        "win_rate": 0.511,
        "profit_factor": 0.948,
        "edge_vs_all": -968.37,
        "stability_frac": 1.0,
        "stability_years": 3
      }
    ]
  },
  "P2_size_tiers": {
    "rule": "2x S_1_1_3 block in listed cells, 1x elsewhere",
    "mechanism": "date-list split, one replay per tier (2x = 2/2/6, entry 10)",
    "tier2_cells": []
  },
  "P3_no_runner": {
    "rule": "use 1/1/0 (no runner) when P(2R|1R) in state trails pooled by >=5pts",
    "mechanism": "date-list split, no-runner tier replay (1/1/0, entry 2)",
    "p_2r_given_1r_pooled": 0.502,
    "cells": [
      {
        "dim": "or_width_q",
        "value": "q4",
        "n": 514,
        "p_2r_given_1r": 0.368
      }
    ]
  },
  "P4_early_cut": {
    "rule": "flatten at OR re-entry when it fires within the empirical cutoff before 1R",
    "mechanism": "requires small v2b_scaleout config flag (not replayed here)",
    "empirical_cutoff_bars5_p75": 2.0,
    "failed_break_sessions_fit": 296,
    "failed_break_mean_net_fit": -4820.02
  },
  "P8_runner_ladder": {
    "rule": "runner to 3R when chain>=0.30; no runner when chain<0.18; else baseline 1/1/3",
    "mechanism": "date-list tiers + runner_target_r_mult=3.0 on runner_3r tier",
    "chain_high": 0.3,
    "chain_low": 0.18,
    "pair_cells": [
      {
        "or_width_q": "q1",
        "gap_bucket": "flat",
        "n1": 94,
        "n2": 51,
        "p_2r_given_1r": 0.543,
        "p_3r_given_2r": 0.549,
        "chain": 0.298,
        "tier": "1x"
      },
      {
        "or_width_q": "q1",
        "gap_bucket": "gap_dn_lg",
        "n1": 48,
        "n2": 28,
        "p_2r_given_1r": 0.583,
        "p_3r_given_2r": 0.571,
        "chain": 0.333,
        "tier": "runner_3r"
      },
      {
        "or_width_q": "q1",
        "gap_bucket": "gap_dn_sm",
        "n1": 92,
        "n2": 52,
        "p_2r_given_1r": 0.565,
        "p_3r_given_2r": 0.519,
        "chain": 0.293,
        "tier": "1x"
      },
      {
        "or_width_q": "q1",
        "gap_bucket": "gap_up_lg",
        "n1": 105,
        "n2": 69,
        "p_2r_given_1r": 0.657,
        "p_3r_given_2r": 0.594,
        "chain": 0.39,
        "tier": "runner_3r"
      },
      {
        "or_width_q": "q1",
        "gap_bucket": "gap_up_sm",
        "n1": 156,
        "n2": 102,
        "p_2r_given_1r": 0.654,
        "p_3r_given_2r": 0.52,
        "chain": 0.34,
        "tier": "runner_3r"
      },
      {
        "or_width_q": "q2",
        "gap_bucket": "flat",
        "n1": 96,
        "n2": 54,
        "p_2r_given_1r": 0.562,
        "p_3r_given_2r": 0.537,
        "chain": 0.302,
        "tier": "runner_3r"
      },
      {
        "or_width_q": "q2",
        "gap_bucket": "gap_dn_lg",
        "n1": 39,
        "n2": 20,
        "p_2r_given_1r": 0.513,
        "p_3r_given_2r": 0.3,
        "chain": 0.154,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q2",
        "gap_bucket": "gap_dn_sm",
        "n1": 100,
        "n2": 57,
        "p_2r_given_1r": 0.57,
        "p_3r_given_2r": 0.439,
        "chain": 0.25,
        "tier": "1x"
      },
      {
        "or_width_q": "q2",
        "gap_bucket": "gap_up_lg",
        "n1": 97,
        "n2": 57,
        "p_2r_given_1r": 0.588,
        "p_3r_given_2r": 0.544,
        "chain": 0.32,
        "tier": "runner_3r"
      },
      {
        "or_width_q": "q2",
        "gap_bucket": "gap_up_sm",
        "n1": 146,
        "n2": 74,
        "p_2r_given_1r": 0.507,
        "p_3r_given_2r": 0.338,
        "chain": 0.171,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q3",
        "gap_bucket": "flat",
        "n1": 74,
        "n2": 31,
        "p_2r_given_1r": 0.419,
        "p_3r_given_2r": 0.548,
        "chain": 0.23,
        "tier": "1x"
      },
      {
        "or_width_q": "q3",
        "gap_bucket": "gap_dn_lg",
        "n1": 60,
        "n2": 37,
        "p_2r_given_1r": 0.617,
        "p_3r_given_2r": 0.405,
        "chain": 0.25,
        "tier": "1x"
      },
      {
        "or_width_q": "q3",
        "gap_bucket": "gap_dn_sm",
        "n1": 83,
        "n2": 37,
        "p_2r_given_1r": 0.446,
        "p_3r_given_2r": 0.432,
        "chain": 0.193,
        "tier": "1x"
      },
      {
        "or_width_q": "q3",
        "gap_bucket": "gap_up_lg",
        "n1": 90,
        "n2": 44,
        "p_2r_given_1r": 0.489,
        "p_3r_given_2r": 0.432,
        "chain": 0.211,
        "tier": "1x"
      },
      {
        "or_width_q": "q3",
        "gap_bucket": "gap_up_sm",
        "n1": 134,
        "n2": 62,
        "p_2r_given_1r": 0.463,
        "p_3r_given_2r": 0.355,
        "chain": 0.164,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q4",
        "gap_bucket": "flat",
        "n1": 84,
        "n2": 30,
        "p_2r_given_1r": 0.357,
        "p_3r_given_2r": 0.267,
        "chain": 0.095,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q4",
        "gap_bucket": "gap_dn_lg",
        "n1": 109,
        "n2": 41,
        "p_2r_given_1r": 0.376,
        "p_3r_given_2r": 0.268,
        "chain": 0.101,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q4",
        "gap_bucket": "gap_dn_sm",
        "n1": 117,
        "n2": 40,
        "p_2r_given_1r": 0.342,
        "p_3r_given_2r": 0.4,
        "chain": 0.137,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q4",
        "gap_bucket": "gap_up_lg",
        "n1": 77,
        "n2": 29,
        "p_2r_given_1r": 0.377,
        "p_3r_given_2r": 0.345,
        "chain": 0.13,
        "tier": "no_runner"
      },
      {
        "or_width_q": "q4",
        "gap_bucket": "gap_up_sm",
        "n1": 127,
        "n2": 49,
        "p_2r_given_1r": 0.386,
        "p_3r_given_2r": 0.347,
        "chain": 0.134,
        "tier": "no_runner"
      }
    ],
    "q_fallback": {
      "q1": "runner_3r",
      "q2": "1x",
      "q3": "1x",
      "q4": "no_runner"
    }
  },
  "P9_reverse_only_when": {
    "rule": "suppress reverse leg outside q1-morning edge states",
    "mechanism": "v2b_scaleout reverse_only_when + session_or_width_q map",
    "variants": {
      "time_1200": {
        "max_first_leg_exit_time": "12:00"
      },
      "time_q1q2": {
        "max_first_leg_exit_time": "12:00",
        "or_width_q_allow": [
          "q1",
          "q2"
        ]
      },
      "q1_only": {
        "or_width_q_allow": [
          "q1"
        ]
      }
    }
  }
}
```

## MNQ

Fit sessions joined: 679 (2021-03-04 -> 2024-12-31), mean net/session $61.75

### v2b expectancy by terminal day label (fit, diagnostic — EOD-knowable)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years |
|---|---|---|---|---|---|---|---|---|---|
| label=double_fail_range | 195 | -152934.0 | -784.28 | -768.5 | 0.154 | 0.117 | -846.03 | 1.0 | 4 |
| label=one_r_reversal | 123 | -29835.5 | -242.57 | -333.5 | 0.374 | 0.536 | -304.32 | 1.0 | 3 |
| label=fakeout_opposite | 38 | 1960.5 | 51.59 | -146.5 | 0.447 | 1.203 | -10.16 | 0.5 | 2 |
| label=break_revert | 158 | 50050.0 | 316.77 | 235.0 | 0.835 | 5.046 | 255.02 | 1.0 | 3 |
| label=break_hold_no1r | 3 | 1294.0 | 431.33 | 332.5 | 1.0 | inf | 369.58 |  | 0 |
| label=clean_break_1r | 18 | 17742.0 | 985.67 | 817.75 | 1.0 | inf | 923.91 |  | 0 |
| label=break_extend_2r | 144 | 153654.0 | 1067.04 | 1038.25 | 0.993 | 4587.687 | 1005.29 | 1.0 | 3 |

### v2b expectancy by pre-entry state (fit)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years | knowable |
|---|---|---|---|---|---|---|---|---|---|---|
| or_width_q=q4|gap_bucket=gap_up_lg | 24 | -5382.5 | -224.27 | 122.5 | 0.583 | 0.673 | -286.02 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_sm | 41 | -8028.0 | -195.8 | 48.5 | 0.537 | 0.731 | -257.56 | 1.0 | 2 | 0945 |
| or_width_q=q1|gap_bucket=flat | 42 | -6740.5 | -160.49 | -308.75 | 0.405 | 0.57 | -222.24 | 1.0 | 2 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_sm | 33 | -5013.0 | -151.91 | -220.0 | 0.485 | 0.604 | -213.66 | 1.0 | 2 | 0945 |
| or_width_q=q4|gap_bucket=flat | 27 | -1473.0 | -54.56 | 163.0 | 0.556 | 0.911 | -116.31 | 1.0 | 1 | 0945 |
| gap_bucket=gap_dn_sm | 143 | -6170.5 | -43.15 | 85.0 | 0.545 | 0.905 | -104.9 | 0.667 | 3 | 0945 |
| or_width_q=q3|gap_bucket=flat | 24 | -843.0 | -35.12 | -247.5 | 0.5 | 0.928 | -96.88 |  | 0 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_sm | 34 | -1070.5 | -31.49 | -24.0 | 0.5 | 0.907 | -93.24 | 0.5 | 2 | 0945 |
| gap_bucket=flat | 138 | -3535.5 | -25.62 | 11.5 | 0.507 | 0.938 | -87.37 | 1.0 | 3 | 0945 |
| or_width_q=q4|gap_bucket=gap_up_sm | 56 | -372.0 | -6.64 | 247.5 | 0.571 | 0.987 | -68.4 | 0.5 | 2 | 0945 |
| or_loc_bucket=mid_third | 151 | -22.5 | -0.15 | 90.5 | 0.543 | 1.0 | -61.9 | 0.667 | 3 | 0945 |
| or_width_q=q4 | 175 | 356.0 | 2.03 | 172.0 | 0.571 | 1.003 | -59.72 | 0.5 | 4 | 0945 |
| or_width_q=q1 | 180 | 1686.0 | 9.37 | 30.75 | 0.511 | 1.032 | -52.39 | 1.0 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_lg | 23 | 403.5 | 17.54 | 78.5 | 0.609 | 1.083 | -44.21 | 0.0 | 1 | 0945 |
| or_loc_bucket=upper_third | 176 | 8305.5 | 47.19 | 45.75 | 0.517 | 1.116 | -14.56 | 0.667 | 3 | 0945 |
| or_loc_bucket=lower_third | 106 | 5951.5 | 56.15 | 106.75 | 0.575 | 1.141 | -5.61 | 0.333 | 3 | 0945 |
| or_loc_bucket=below_prior | 94 | 5615.5 | 59.74 | 128.0 | 0.617 | 1.136 | -2.01 | 0.667 | 3 | 0945 |
| gap_bucket=gap_up_sm | 203 | 17526.5 | 86.34 | 137.0 | 0.581 | 1.245 | 24.58 | 0.667 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_sm | 55 | 4953.5 | 90.06 | 19.5 | 0.527 | 1.391 | 28.31 | 0.0 | 2 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_sm | 46 | 4949.5 | 107.6 | 135.25 | 0.543 | 1.289 | 45.84 | 0.5 | 2 | 0945 |
| gap_bucket=gap_up_lg | 110 | 12105.5 | 110.05 | 175.25 | 0.618 | 1.31 | 48.3 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_lg | 11 | 1243.0 | 113.0 | 101.0 | 0.727 | 1.538 | 51.25 |  | 0 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_lg | 15 | 1826.0 | 121.73 | 236.0 | 0.6 | 1.279 | 59.98 |  | 0 | 0945 |
| or_width_q=q2 | 134 | 16942.0 | 126.43 | 111.5 | 0.634 | 1.474 | 64.68 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_lg | 21 | 2924.0 | 139.24 | 111.0 | 0.667 | 1.565 | 77.48 | 1.0 | 1 | 0945 |
| or_loc_bucket=above_prior | 151 | 23032.5 | 152.53 | 211.5 | 0.642 | 1.467 | 90.78 | 1.0 | 3 | 0945 |
| or_width_q=q3 | 140 | 21871.0 | 156.22 | 140.5 | 0.593 | 1.428 | 94.47 | 0.667 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_lg | 26 | 4140.0 | 159.23 | 174.25 | 0.577 | 1.562 | 97.48 | 1.0 | 1 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_sm | 36 | 8106.0 | 225.17 | 252.0 | 0.722 | 1.944 | 163.41 | 1.0 | 2 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_lg | 28 | 7375.0 | 263.39 | 273.75 | 0.643 | 1.863 | 201.64 | 1.0 | 1 | 0945 |
| gap_bucket=gap_dn_lg | 84 | 22956.5 | 273.29 | 202.25 | 0.655 | 1.888 | 211.54 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=flat | 33 | 9682.0 | 293.39 | 147.5 | 0.636 | 2.383 | 231.64 | 1.0 | 2 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_sm | 27 | 8563.5 | 317.17 | 142.0 | 0.704 | 2.206 | 255.41 | 1.0 | 2 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_lg | 27 | 15611.5 | 578.2 | 572.5 | 0.63 | 2.494 | 516.45 | 1.0 | 1 | 0945 |

### Frozen policies

```json
{
  "P1_skip": {
    "rule": "skip session when any cell matches (state knowable at 09:45)",
    "mechanism": "regime_dates restriction",
    "cells": [
      {
        "dim": "gap_bucket",
        "value": "flat",
        "condition": "gap_bucket=flat",
        "n_sessions": 138,
        "total_net": -3535.5,
        "mean_net": -25.62,
        "median_net": 11.5,
        "win_rate": 0.507,
        "profit_factor": 0.938,
        "edge_vs_all": -87.37,
        "stability_frac": 1.0,
        "stability_years": 3
      }
    ]
  },
  "P2_size_tiers": {
    "rule": "2x S_1_1_3 block in listed cells, 1x elsewhere",
    "mechanism": "date-list split, one replay per tier (2x = 2/2/6, entry 10)",
    "tier2_cells": []
  },
  "P3_no_runner": {
    "rule": "use 1/1/0 (no runner) when P(2R|1R) in state trails pooled by >=5pts",
    "mechanism": "date-list split, no-runner tier replay (1/1/0, entry 2)",
    "p_2r_given_1r_pooled": 0.495,
    "cells": [
      {
        "dim": "or_width_q",
        "value": "q4",
        "n": 112,
        "p_2r_given_1r": 0.268
      }
    ]
  },
  "P4_early_cut": {
    "rule": "flatten at OR re-entry when it fires within the empirical cutoff before 1R",
    "mechanism": "requires small v2b_scaleout config flag (not replayed here)",
    "empirical_cutoff_bars5_p75": 2.0,
    "failed_break_sessions_fit": 297,
    "failed_break_mean_net_fit": -501.55
  },
  "P8_runner_ladder": {
    "rule": "runner to 3R when chain>=0.30; no runner when chain<0.18; else baseline 1/1/3",
    "mechanism": "date-list tiers + runner_target_r_mult=3.0 on runner_3r tier",
    "chain_high": 0.3,
    "chain_low": 0.18,
    "pair_cells": [
      {
        "or_width_q": "q1",
        "gap_bucket": "gap_up_sm",
        "n1": 42,
        "n2": 29,
        "p_2r_given_1r": 0.69,
        "p_3r_given_2r": 0.517,
        "chain": 0.357,
        "tier": "runner_3r"
      }
    ],
    "q_fallback": {
      "q1": "runner_3r",
      "q2": "1x",
      "q3": "1x",
      "q4": "no_runner"
    }
  },
  "P9_reverse_only_when": {
    "rule": "suppress reverse leg outside q1-morning edge states",
    "mechanism": "v2b_scaleout reverse_only_when + session_or_width_q map",
    "variants": {
      "time_1200": {
        "max_first_leg_exit_time": "12:00"
      },
      "time_q1q2": {
        "max_first_leg_exit_time": "12:00",
        "or_width_q_allow": [
          "q1",
          "q2"
        ]
      },
      "q1_only": {
        "or_width_q_allow": [
          "q1"
        ]
      }
    }
  }
}
```