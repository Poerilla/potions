# OR Profile -> v2b S_1_1_3 join (2026H2)

Trigger = `touch` (matches v2b stop fills). Fit window = tape start -> 2025-06-30; policies are derived on the fit window only and frozen in `policies.json`.

## NQ

Fit sessions joined: 742 (2021-03-04 -> 2025-06-30), mean net/session $850.32

### v2b expectancy by terminal day label (fit, diagnostic — EOD-knowable)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years |
|---|---|---|---|---|---|---|---|---|---|
| label=double_fail_range | 210 | -1731955.0 | -8247.4 | -7620.0 | 0.152 | 0.112 | -9097.72 | 1.0 | 5 |
| label=one_r_reversal | 138 | -301837.5 | -2187.23 | -3070.0 | 0.391 | 0.577 | -3037.54 | 1.0 | 4 |
| label=fakeout_opposite | 38 | 33545.0 | 882.76 | -235.0 | 0.474 | 1.383 | 32.45 | 0.667 | 3 |
| label=break_revert | 174 | 638742.5 | 3670.93 | 2567.5 | 0.845 | 6.202 | 2820.62 | 1.0 | 4 |
| label=break_hold_no1r | 3 | 13317.5 | 4439.17 | 3435.0 | 1.0 | inf | 3588.85 |  | 0 |
| label=clean_break_1r | 20 | 197485.0 | 9874.25 | 8260.0 | 1.0 | inf | 9023.93 |  | 0 |
| label=break_extend_2r | 159 | 1781637.5 | 11205.27 | 10487.5 | 0.994 | 6092.068 | 10354.95 | 1.0 | 4 |

### v2b expectancy by pre-entry state (fit)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years | knowable |
|---|---|---|---|---|---|---|---|---|---|---|
| or_width_q=q4|gap_bucket=gap_up_lg | 32 | -78287.5 | -2446.48 | 1336.25 | 0.531 | 0.676 | -3296.8 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_sm | 44 | -105592.5 | -2399.83 | 396.25 | 0.523 | 0.685 | -3250.15 | 1.0 | 2 | 0945 |
| or_width_q=q1|gap_bucket=flat | 48 | -66702.5 | -1389.64 | -2297.5 | 0.438 | 0.596 | -2239.95 | 1.0 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_sm | 36 | -46525.0 | -1292.36 | -292.5 | 0.5 | 0.641 | -2142.68 | 0.5 | 2 | 0945 |
| or_width_q=q4|gap_bucket=flat | 38 | -44817.5 | -1179.41 | 1065.0 | 0.526 | 0.822 | -2029.72 | 1.0 | 2 | 0945 |
| gap_bucket=gap_dn_sm | 148 | -66035.0 | -446.18 | 991.25 | 0.541 | 0.9 | -1296.5 | 0.667 | 3 | 0945 |
| or_width_q=q3|gap_bucket=flat | 31 | -10095.0 | -325.65 | -4990.0 | 0.484 | 0.937 | -1175.96 | 1.0 | 1 | 0945 |
| gap_bucket=flat | 153 | -34482.5 | -225.38 | 442.5 | 0.516 | 0.948 | -1075.69 | 1.0 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_sm | 40 | -7135.0 | -178.38 | -31.25 | 0.5 | 0.94 | -1028.69 | 0.5 | 2 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_lg | 13 | -1947.5 | -149.81 | 1077.5 | 0.692 | 0.951 | -1000.12 |  | 0 | 0945 |
| or_loc_bucket=lower_third | 118 | 10925.0 | 92.58 | 1050.0 | 0.542 | 1.02 | -757.73 | 0.75 | 4 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_sm | 42 | 9940.0 | 236.67 | 1277.5 | 0.619 | 1.063 | -613.65 | 0.667 | 3 | 0945 |
| or_width_q=q1 | 199 | 88790.0 | 446.18 | 637.5 | 0.533 | 1.171 | -404.14 | 1.0 | 3 | 0945 |
| or_loc_bucket=upper_third | 186 | 84042.5 | 451.84 | 722.5 | 0.522 | 1.106 | -398.48 | 0.75 | 4 | 0945 |
| or_width_q=q4 | 216 | 98870.0 | 457.73 | 2192.5 | 0.583 | 1.077 | -392.59 | 0.6 | 5 | 0945 |
| or_loc_bucket=mid_third | 164 | 81610.0 | 497.62 | 1070.0 | 0.567 | 1.143 | -352.69 | 0.5 | 4 | 0945 |
| or_width_q=q2 | 156 | 113350.0 | 726.6 | 1137.5 | 0.622 | 1.241 | -123.71 | 0.5 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_lg | 26 | 21457.5 | 825.29 | 897.5 | 0.654 | 1.451 | -25.03 | 0.0 | 1 | 0945 |
| gap_bucket=gap_up_lg | 123 | 103662.5 | 842.78 | 1917.5 | 0.618 | 1.221 | -7.53 | 0.5 | 4 | 0945 |
| or_loc_bucket=below_prior | 105 | 139940.0 | 1332.76 | 1717.5 | 0.638 | 1.329 | 482.45 | 0.333 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_lg | 27 | 36232.5 | 1341.94 | 1485.0 | 0.556 | 1.454 | 491.63 | 0.0 | 1 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_lg | 24 | 35417.5 | 1475.73 | 2058.75 | 0.583 | 1.316 | 625.41 |  | 0 | 0945 |
| or_width_q=q4|gap_bucket=gap_up_sm | 68 | 103092.5 | 1516.07 | 3080.0 | 0.618 | 1.306 | 665.75 | 0.667 | 3 | 0945 |
| gap_bucket=gap_up_sm | 221 | 348387.5 | 1576.41 | 2112.5 | 0.602 | 1.453 | 726.1 | 0.75 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_sm | 58 | 104937.5 | 1809.27 | 825.0 | 0.569 | 1.982 | 958.95 | 0.667 | 3 | 0945 |
| or_loc_bucket=above_prior | 169 | 314417.5 | 1860.46 | 2415.0 | 0.657 | 1.577 | 1010.14 | 1.0 | 4 | 0945 |
| or_width_q=q3 | 171 | 329925.0 | 1929.39 | 1667.5 | 0.602 | 1.542 | 1079.07 | 0.75 | 4 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_lg | 29 | 64750.0 | 2232.76 | 2295.0 | 0.724 | 2.139 | 1382.44 | 1.0 | 1 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_lg | 35 | 80967.5 | 2313.36 | 3567.5 | 0.657 | 1.894 | 1463.04 | 0.5 | 2 | 0945 |
| or_width_q=q2|gap_bucket=flat | 36 | 87132.5 | 2420.35 | 1725.0 | 0.639 | 1.989 | 1570.03 | 0.667 | 3 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_sm | 53 | 130417.5 | 2460.71 | 2112.5 | 0.604 | 1.777 | 1610.39 | 0.5 | 2 | 0945 |
| gap_bucket=gap_dn_lg | 97 | 279402.5 | 2880.44 | 2142.5 | 0.66 | 1.902 | 2030.12 | 0.75 | 4 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_sm | 28 | 93217.5 | 3329.2 | 4180.0 | 0.679 | 2.19 | 2478.88 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_lg | 34 | 224475.0 | 6602.21 | 8276.25 | 0.706 | 3.028 | 5751.89 | 1.0 | 2 | 0945 |

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
        "n_sessions": 153,
        "total_net": -34482.5,
        "mean_net": -225.38,
        "median_net": 442.5,
        "win_rate": 0.516,
        "profit_factor": 0.948,
        "edge_vs_all": -1075.69,
        "stability_frac": 1.0,
        "stability_years": 4
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
    "p_2r_given_1r_pooled": 0.5,
    "cells": [
      {
        "dim": "or_width_q",
        "value": "q4",
        "n": 541,
        "p_2r_given_1r": 0.368
      }
    ]
  },
  "P4_early_cut": {
    "rule": "flatten at OR re-entry when it fires within the empirical cutoff before 1R",
    "mechanism": "requires small v2b_scaleout config flag (not replayed here)",
    "empirical_cutoff_bars5_p75": 2.0,
    "failed_break_sessions_fit": 314,
    "failed_break_mean_net_fit": -5313.63
  }
}
```

## MNQ

Fit sessions joined: 741 (2021-03-04 -> 2025-06-30), mean net/session $71.17

### v2b expectancy by terminal day label (fit, diagnostic — EOD-knowable)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years |
|---|---|---|---|---|---|---|---|---|---|
| label=double_fail_range | 211 | -177401.5 | -840.77 | -787.5 | 0.156 | 0.109 | -911.93 | 1.0 | 5 |
| label=one_r_reversal | 136 | -31507.0 | -231.67 | -330.25 | 0.39 | 0.559 | -302.84 | 1.0 | 4 |
| label=fakeout_opposite | 38 | 1960.5 | 51.59 | -146.5 | 0.447 | 1.203 | -19.58 | 0.5 | 2 |
| label=break_revert | 173 | 61155.0 | 353.5 | 247.5 | 0.844 | 5.911 | 282.33 | 1.0 | 4 |
| label=break_hold_no1r | 3 | 1294.0 | 431.33 | 332.5 | 1.0 | inf | 360.17 |  | 0 |
| label=clean_break_1r | 20 | 19267.0 | 963.35 | 817.75 | 1.0 | inf | 892.18 |  | 0 |
| label=break_extend_2r | 160 | 177967.0 | 1112.29 | 1044.25 | 0.994 | 5313.448 | 1041.13 | 1.0 | 4 |

### v2b expectancy by pre-entry state (fit)

| condition | n_sessions | total_net | mean_net | median_net | win_rate | profit_factor | edge_vs_all | stability_frac | stability_years | knowable |
|---|---|---|---|---|---|---|---|---|---|---|
| or_width_q=q4|gap_bucket=gap_up_lg | 30 | -11764.5 | -392.15 | 102.5 | 0.533 | 0.518 | -463.32 | 1.0 | 1 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_sm | 44 | -8813.0 | -200.3 | 76.75 | 0.545 | 0.721 | -271.46 | 1.0 | 2 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_sm | 35 | -5941.5 | -169.76 | -220.0 | 0.486 | 0.577 | -240.92 | 1.0 | 2 | 0945 |
| or_width_q=q1|gap_bucket=flat | 45 | -6337.5 | -140.83 | -277.5 | 0.422 | 0.607 | -212.0 | 1.0 | 2 | 0945 |
| or_width_q=q4|gap_bucket=flat | 34 | -4478.5 | -131.72 | 102.75 | 0.529 | 0.811 | -202.89 | 1.0 | 1 | 0945 |
| gap_bucket=gap_dn_sm | 149 | -7714.0 | -51.77 | 89.5 | 0.55 | 0.886 | -122.94 | 0.667 | 3 | 0945 |
| or_width_q=q2|gap_bucket=gap_dn_lg | 12 | -407.0 | -33.92 | 99.75 | 0.667 | 0.897 | -105.08 |  | 0 | 0945 |
| gap_bucket=flat | 152 | -4214.5 | -27.73 | 28.5 | 0.513 | 0.937 | -98.89 | 1.0 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_sm | 35 | -900.5 | -25.73 | 49.5 | 0.514 | 0.921 | -96.9 | 0.5 | 2 | 0945 |
| or_width_q=q4 | 206 | -1576.5 | -7.65 | 196.5 | 0.573 | 0.988 | -78.82 | 0.8 | 5 | 0945 |
| or_width_q=q1 | 187 | 2884.5 | 15.43 | 48.5 | 0.524 | 1.055 | -55.74 | 1.0 | 3 | 0945 |
| or_width_q=q1|gap_bucket=gap_dn_lg | 24 | 490.5 | 20.44 | 78.5 | 0.625 | 1.101 | -50.73 | 0.0 | 1 | 0945 |
| or_loc_bucket=lower_third | 119 | 2901.0 | 24.38 | 103.0 | 0.555 | 1.055 | -46.79 | 0.75 | 4 | 0945 |
| or_loc_bucket=mid_third | 163 | 5501.5 | 33.75 | 98.5 | 0.564 | 1.094 | -37.42 | 0.5 | 4 | 0945 |
| or_width_q=q3|gap_bucket=flat | 28 | 1080.5 | 38.59 | 72.25 | 0.536 | 1.078 | -32.58 |  | 0 | 0945 |
| or_loc_bucket=upper_third | 187 | 7461.0 | 39.9 | 82.0 | 0.524 | 1.094 | -31.27 | 0.75 | 4 | 0945 |
| gap_bucket=gap_up_lg | 123 | 7743.0 | 62.95 | 182.0 | 0.618 | 1.162 | -8.22 | 0.5 | 4 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_sm | 56 | 5172.5 | 92.37 | 33.0 | 0.536 | 1.408 | 21.2 | 0.0 | 2 | 0945 |
| or_loc_bucket=below_prior | 103 | 9633.5 | 93.53 | 141.5 | 0.631 | 1.213 | 22.36 | 0.333 | 3 | 0945 |
| or_width_q=q2 | 143 | 15215.5 | 106.4 | 112.0 | 0.629 | 1.38 | 35.23 | 0.667 | 3 | 0945 |
| or_width_q=q4|gap_bucket=gap_up_sm | 66 | 7563.5 | 114.6 | 293.75 | 0.606 | 1.222 | 43.43 | 0.667 | 3 | 0945 |
| gap_bucket=gap_up_sm | 221 | 32162.5 | 145.53 | 202.5 | 0.602 | 1.415 | 74.36 | 0.75 | 4 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_lg | 25 | 3930.5 | 157.22 | 168.5 | 0.68 | 1.671 | 86.05 | 1.0 | 1 | 0945 |
| or_width_q=q1|gap_bucket=gap_up_lg | 27 | 4459.5 | 165.17 | 211.5 | 0.593 | 1.606 | 94.0 | 0.0 | 1 | 0945 |
| or_loc_bucket=above_prior | 168 | 28189.5 | 167.79 | 220.0 | 0.655 | 1.509 | 96.63 | 0.75 | 4 | 0945 |
| or_width_q=q2|gap_bucket=gap_up_sm | 38 | 7951.5 | 209.25 | 252.0 | 0.711 | 1.868 | 138.08 | 1.0 | 2 | 0945 |
| or_width_q=q3 | 155 | 35135.5 | 226.68 | 182.0 | 0.619 | 1.66 | 155.51 | 0.75 | 4 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_sm | 51 | 11585.5 | 227.17 | 204.5 | 0.588 | 1.676 | 156.0 | 0.5 | 2 | 0945 |
| or_width_q=q3|gap_bucket=gap_up_lg | 30 | 8068.5 | 268.95 | 273.75 | 0.667 | 1.944 | 197.78 | 1.0 | 1 | 0945 |
| gap_bucket=gap_dn_lg | 95 | 25709.5 | 270.63 | 189.5 | 0.653 | 1.817 | 199.46 | 0.75 | 4 | 0945 |
| or_width_q=q2|gap_bucket=flat | 33 | 9682.0 | 293.39 | 147.5 | 0.636 | 2.383 | 222.23 | 1.0 | 2 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_lg | 19 | 5837.5 | 307.24 | 236.0 | 0.632 | 1.881 | 236.07 |  | 0 | 0945 |
| or_width_q=q3|gap_bucket=gap_dn_sm | 27 | 8563.5 | 317.17 | 142.0 | 0.704 | 2.206 | 246.0 | 1.0 | 2 | 0945 |
| or_width_q=q4|gap_bucket=gap_dn_lg | 32 | 15916.0 | 497.38 | 461.0 | 0.625 | 2.111 | 426.21 | 1.0 | 1 | 0945 |

### Frozen policies

```json
{
  "P1_skip": {
    "rule": "skip session when any cell matches (state knowable at 09:45)",
    "mechanism": "regime_dates restriction",
    "cells": [
      {
        "dim": "or_width_q",
        "value": "q4",
        "condition": "or_width_q=q4",
        "n_sessions": 206,
        "total_net": -1576.5,
        "mean_net": -7.65,
        "median_net": 196.5,
        "win_rate": 0.573,
        "profit_factor": 0.988,
        "edge_vs_all": -78.82,
        "stability_frac": 0.8,
        "stability_years": 5
      },
      {
        "dim": "gap_bucket",
        "value": "flat",
        "condition": "gap_bucket=flat",
        "n_sessions": 152,
        "total_net": -4214.5,
        "mean_net": -27.73,
        "median_net": 28.5,
        "win_rate": 0.513,
        "profit_factor": 0.937,
        "edge_vs_all": -98.89,
        "stability_frac": 1.0,
        "stability_years": 4
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
    "p_2r_given_1r_pooled": 0.489,
    "cells": [
      {
        "dim": "or_width_q",
        "value": "q4",
        "n": 139,
        "p_2r_given_1r": 0.288
      }
    ]
  },
  "P4_early_cut": {
    "rule": "flatten at OR re-entry when it fires within the empirical cutoff before 1R",
    "mechanism": "requires small v2b_scaleout config flag (not replayed here)",
    "empirical_cutoff_bars5_p75": 2.0,
    "failed_break_sessions_fit": 315,
    "failed_break_mean_net_fit": -550.81
  }
}
```