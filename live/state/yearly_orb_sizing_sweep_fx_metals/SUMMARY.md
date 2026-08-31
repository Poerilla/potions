# Yearly ORB Scaleout3 Sizing Sweep

Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for 
`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` 
path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, per-market fees 
(futures/metals $1.50; AUDJPY ¥7), stop gap-through ON, stop-first same-bar, 
OCO-collapsed risk projection.

Ranking is by `Net / Stress DD` (currency-invariant). AUDJPY ~USD uses ÷110.

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | AUDJPY | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 876 | 146 | ¥46,217,168 (~$420,156) | ¥-1,858,200 (~$-16,893) | 24.87 |
| 2 | AUDJPY | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 1168 | 146 | ¥61,404,299 (~$558,221) | ¥-2,477,600 (~$-22,524) | 24.78 |
| 3 | AUDJPY | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 1022 | 146 | ¥53,043,146 (~$482,210) | ¥-2,328,470 (~$-21,168) | 22.78 |
| 4 | AUDJPY | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 876 | 146 | ¥44,681,993 (~$406,200) | ¥-2,227,863 (~$-20,253) | 20.06 |
| 5 | AUDJPY | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 1168 | 146 | ¥58,989,724 (~$536,270) | ¥-2,970,484 (~$-27,004) | 19.86 |
| 6 | AUDJPY | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 584 | 146 | ¥29,494,862 (~$268,135) | ¥-1,485,242 (~$-13,502) | 19.86 |
| 7 | AUDJPY | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 1022 | 146 | ¥49,749,171 (~$452,265) | ¥-3,109,142 (~$-28,265) | 16.00 |
| 8 | XAUUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 637 | 91 | $1,037,710.80 | $-67,741.50 | 15.32 |
| 9 | AUDJPY | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 876 | 146 | ¥42,267,418 (~$384,249) | ¥-2,769,270 (~$-25,175) | 15.26 |
| 10 | AUDJPY | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 1314 | 146 | ¥63,401,127 (~$576,374) | ¥-4,153,905 (~$-37,763) | 15.26 |
| 11 | AUDJPY | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 438 | 146 | ¥21,133,709 (~$192,125) | ¥-1,384,635 (~$-12,588) | 15.26 |
| 12 | XAUUSD | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 728 | 91 | $1,146,459.65 | $-75,130.50 | 15.26 |
| 13 | XAUUSD | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 546 | 91 | $928,961.95 | $-62,346.90 | 14.90 |
| 14 | AUDJPY | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 1022 | 146 | ¥49,972,796 (~$454,298) | ¥-3,411,284 (~$-31,012) | 14.65 |
| 15 | XAUUSD | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 546 | 91 | $867,500.90 | $-60,352.50 | 14.37 |
| 16 | XAUUSD | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 364 | 91 | $650,003.20 | $-47,902.60 | 13.57 |
| 17 | XAUUSD | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 728 | 91 | $1,300,006.40 | $-95,805.20 | 13.57 |
| 18 | AUDJPY | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 1168 | 146 | ¥54,160,574 (~$492,369) | ¥-4,508,642 (~$-40,988) | 12.01 |
| 19 | AUDJPY | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 1022 | 146 | ¥46,678,821 (~$424,353) | ¥-3,952,691 (~$-35,934) | 11.81 |
| 20 | XAUUSD | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 637 | 91 | $1,160,632.90 | $-99,545.00 | 11.66 |
| 21 | XAUUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 273 | 91 | $541,254.35 | $-47,902.60 | 11.30 |
| 22 | XAUUSD | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 546 | 91 | $1,082,508.70 | $-95,805.20 | 11.30 |
| 23 | XAUUSD | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 819 | 91 | $1,623,763.05 | $-143,707.80 | 11.30 |
| 24 | AUDJPY | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 1022 | 146 | ¥45,799,421 (~$416,358) | ¥-4,625,335 (~$-42,049) | 9.90 |
| 25 | AUDJPY | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 730 | 146 | ¥33,026,865 (~$300,244) | ¥-3,342,528 (~$-30,387) | 9.88 |
| 26 | XAUUSD | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 637 | 91 | $1,406,265.35 | $-143,707.80 | 9.79 |
| 27 | XAUUSD | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 637 | 91 | $1,283,343.25 | $-143,707.80 | 8.93 |
| 28 | XAGUSD | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 712 | 89 | $301,375.75 | $-35,142.50 | 8.58 |
| 29 | XAGUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 623 | 89 | $268,625.50 | $-32,015.50 | 8.39 |
| 30 | XAUUSD | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 728 | 91 | $1,607,099.90 | $-191,610.40 | 8.39 |
| 31 | XAGUSD | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 534 | 89 | $235,875.25 | $-28,888.50 | 8.17 |
| 32 | XAUUSD | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 637 | 91 | $1,498,351.05 | $-191,610.40 | 7.82 |
| 33 | XAGUSD | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 534 | 89 | $219,436.00 | $-28,888.50 | 7.60 |
| 34 | XAUUSD | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 455 | 91 | $1,065,845.55 | $-143,707.80 | 7.42 |
| 35 | XAGUSD | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 623 | 89 | $301,504.00 | $-41,750.00 | 7.22 |
| 36 | XAGUSD | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 712 | 89 | $307,871.00 | $-45,269.00 | 6.80 |
| 37 | XAGUSD | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 356 | 89 | $153,935.50 | $-22,634.50 | 6.80 |
| 38 | XAGUSD | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 534 | 89 | $242,370.50 | $-39,015.00 | 6.21 |
| 39 | XAGUSD | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 801 | 89 | $363,555.75 | $-58,522.50 | 6.21 |
| 40 | XAGUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 267 | 89 | $121,185.25 | $-19,507.50 | 6.21 |
| 41 | XAUUSD | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 308 | 44 | $662,746.40 | $-115,554.00 | 5.74 |
| 42 | XAGUSD | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 623 | 89 | $298,055.25 | $-52,268.50 | 5.70 |
| 43 | XAGUSD | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 623 | 89 | $265,176.75 | $-52,268.50 | 5.07 |
| 44 | XAUUSD | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 132 | 44 | $370,668.85 | $-74,837.17 | 4.95 |
| 45 | XAGUSD | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 712 | 89 | $320,861.50 | $-65,522.00 | 4.90 |
| 46 | XAUUSD | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 162 | 54 | $407,981.62 | $-86,821.10 | 4.70 |
| 47 | XAGUSD | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 623 | 89 | $288,111.25 | $-62,395.00 | 4.62 |
| 48 | XAGUSD | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 445 | 89 | $199,676.25 | $-46,014.50 | 4.34 |
| 49 | XAUUSD | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 378 | 54 | $699,692.70 | $-179,788.00 | 3.89 |
| 50 | XAGUSD | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 329 | 47 | $147,970.50 | $-46,137.00 | 3.21 |
| 51 | XAGUSD | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 141 | 47 | $84,201.75 | $-28,952.50 | 2.91 |
| 52 | XAGUSD | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 177 | 59 | $82,079.00 | $-46,474.00 | 1.77 |
| 53 | XAGUSD | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 413 | 59 | $136,405.50 | $-89,724.00 | 1.52 |
| 54 | AUDJPY | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 441 | 63 | ¥4,547,713 (~$41,343) | ¥-17,457,013 (~$-158,700) | 0.26 |
| 55 | AUDJPY | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 574 | 82 | ¥5,078,082 (~$46,164) | ¥-23,513,052 (~$-213,755) | 0.22 |
| 56 | AUDJPY | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 189 | 63 | ¥345,427 (~$3,140) | ¥-10,208,165 (~$-92,802) | 0.03 |
| 57 | AUDJPY | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 246 | 82 | ¥-714,747 (~$-6,498) | ¥-13,378,433 (~$-121,622) | -0.05 |

## Per-Market Ranking

### AUDJPY

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | ¥46,217,168 | ¥-1,858,200 | 24.87 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | ¥61,404,299 | ¥-2,477,600 | 24.78 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | ¥53,043,146 | ¥-2,328,470 | 22.78 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | ¥44,681,993 | ¥-2,227,863 | 20.06 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | ¥58,989,724 | ¥-2,970,484 | 19.86 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | ¥29,494,862 | ¥-1,485,242 | 19.86 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | ¥49,749,171 | ¥-3,109,142 | 16.00 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | ¥42,267,418 | ¥-2,769,270 | 15.26 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | ¥63,401,127 | ¥-4,153,905 | 15.26 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | ¥21,133,709 | ¥-1,384,635 | 15.26 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | ¥49,972,796 | ¥-3,411,284 | 14.65 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | ¥54,160,574 | ¥-4,508,642 | 12.01 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | ¥46,678,821 | ¥-3,952,691 | 11.81 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | ¥45,799,421 | ¥-4,625,335 | 9.90 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | ¥33,026,865 | ¥-3,342,528 | 9.88 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | ¥4,547,713 | ¥-17,457,013 | 0.26 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | ¥5,078,082 | ¥-23,513,052 | 0.22 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | ¥345,427 | ¥-10,208,165 | 0.03 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | ¥-714,747 | ¥-13,378,433 | -0.05 |

### XAGUSD

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $301,375.75 | $-35,142.50 | 8.58 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $268,625.50 | $-32,015.50 | 8.39 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $235,875.25 | $-28,888.50 | 8.17 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $219,436.00 | $-28,888.50 | 7.60 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $301,504.00 | $-41,750.00 | 7.22 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $307,871.00 | $-45,269.00 | 6.80 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $153,935.50 | $-22,634.50 | 6.80 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $242,370.50 | $-39,015.00 | 6.21 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $363,555.75 | $-58,522.50 | 6.21 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $121,185.25 | $-19,507.50 | 6.21 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $298,055.25 | $-52,268.50 | 5.70 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $265,176.75 | $-52,268.50 | 5.07 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $320,861.50 | $-65,522.00 | 4.90 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $288,111.25 | $-62,395.00 | 4.62 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $199,676.25 | $-46,014.50 | 4.34 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $147,970.50 | $-46,137.00 | 3.21 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $84,201.75 | $-28,952.50 | 2.91 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $82,079.00 | $-46,474.00 | 1.77 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $136,405.50 | $-89,724.00 | 1.52 |

### XAUUSD

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $1,037,710.80 | $-67,741.50 | 15.32 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $1,146,459.65 | $-75,130.50 | 15.26 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $928,961.95 | $-62,346.90 | 14.90 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $867,500.90 | $-60,352.50 | 14.37 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $650,003.20 | $-47,902.60 | 13.57 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $1,300,006.40 | $-95,805.20 | 13.57 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $1,160,632.90 | $-99,545.00 | 11.66 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $541,254.35 | $-47,902.60 | 11.30 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $1,082,508.70 | $-95,805.20 | 11.30 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $1,623,763.05 | $-143,707.80 | 11.30 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $1,406,265.35 | $-143,707.80 | 9.79 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $1,283,343.25 | $-143,707.80 | 8.93 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $1,607,099.90 | $-191,610.40 | 8.39 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $1,498,351.05 | $-191,610.40 | 7.82 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $1,065,845.55 | $-143,707.80 | 7.42 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $662,746.40 | $-115,554.00 | 5.74 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $370,668.85 | $-74,837.17 | 4.95 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $407,981.62 | $-86,821.10 | 4.70 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $699,692.70 | $-179,788.00 | 3.89 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| AUDJPY | limit_retest 4/1/1 | 4/1/1 | ¥46,217,168 | ¥-1,858,200 | 24.87 | +9.61 N/S |
| XAGUSD | limit_retest 5/2/1 | 5/2/1 | $301,375.75 | $-35,142.50 | 8.58 | +2.36 N/S |
| XAUUSD | limit_retest 4/2/1 | 4/2/1 | $1,037,710.80 | $-67,741.50 | 15.32 | +4.02 N/S |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.
- `deep_check/<slug>/` — yearly board + robustness for best-per-market books.
- `winloss_charts/<slug>/` — sampled win/loss charts.
- One-pagers: [`ONE_PAGE_AUDJPY_L_4_1_1.md`](ONE_PAGE_AUDJPY_L_4_1_1.md), [`ONE_PAGE_XAUUSD_L_4_2_1.md`](ONE_PAGE_XAUUSD_L_4_2_1.md), [`ONE_PAGE_XAGUSD_L_5_2_1.md`](ONE_PAGE_XAGUSD_L_5_2_1.md).
- Path / how-we-got-here: [`../../../mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md`](../../../mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md).