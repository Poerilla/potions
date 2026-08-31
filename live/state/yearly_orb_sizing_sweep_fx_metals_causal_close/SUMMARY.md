# Yearly ORB Scaleout3 Sizing Sweep

Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for 
`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` 
path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, per-market fees 
(futures/metals $1.50; AUDJPY ¥7), stop gap-through ON, stop-first same-bar, 
OCO-collapsed risk projection.

Causal market exits: range-close / year-change flatten with 
`live_after_ts=decision_bar.ts` so fills occur on the **next daily open**, 
not the same completed bar's open (lookahead fix).

Ranking is by `Net / Stress DD` (currency-invariant). AUDJPY ~USD uses ÷110.

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | XAUUSD | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 301 | 43 | $521,978.40 | $-166,134.00 | 3.14 |
| 2 | XAUUSD | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 129 | 43 | $310,750.18 | $-105,716.07 | 2.94 |
| 3 | XAUUSD | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 162 | 54 | $327,473.55 | $-124,943.40 | 2.62 |
| 4 | XAUUSD | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 455 | 91 | $512,919.65 | $-242,113.62 | 2.12 |
| 5 | XAUUSD | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 637 | 91 | $715,368.75 | $-342,106.12 | 2.09 |
| 6 | XAUUSD | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 637 | 91 | $540,115.95 | $-258,960.27 | 2.09 |
| 7 | XAUUSD | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 728 | 91 | $728,966.90 | $-350,529.45 | 2.08 |
| 8 | XAUUSD | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 378 | 54 | $508,530.90 | $-246,594.20 | 2.06 |
| 9 | XAUUSD | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 637 | 91 | $620,945.45 | $-308,400.82 | 2.01 |
| 10 | XAUUSD | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 546 | 91 | $432,094.50 | $-216,831.65 | 1.99 |
| 11 | XAUUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 273 | 91 | $216,047.25 | $-108,415.82 | 1.99 |
| 12 | XAUUSD | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 819 | 91 | $648,141.75 | $-325,247.47 | 1.99 |
| 13 | XAUUSD | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 364 | 91 | $229,645.40 | $-116,839.15 | 1.97 |
| 14 | XAUUSD | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 728 | 91 | $459,290.80 | $-233,678.30 | 1.97 |
| 15 | XAUUSD | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 546 | 91 | $256,841.70 | $-136,718.50 | 1.88 |
| 16 | XAUUSD | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 546 | 91 | $297,256.45 | $-158,406.07 | 1.88 |
| 17 | XAUUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 637 | 91 | $310,854.60 | $-166,935.80 | 1.86 |
| 18 | XAUUSD | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 728 | 91 | $324,452.75 | $-177,580.45 | 1.83 |
| 19 | XAUUSD | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 637 | 91 | $391,684.10 | $-216,269.95 | 1.81 |
| 20 | XAGUSD | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 141 | 47 | $62,674.75 | $-41,246.50 | 1.52 |
| 21 | XAGUSD | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 329 | 47 | $100,563.50 | $-68,013.50 | 1.48 |
| 22 | XAGUSD | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 712 | 89 | $75,641.75 | $-56,814.50 | 1.33 |
| 23 | XAGUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 623 | 89 | $65,539.50 | $-50,978.50 | 1.29 |
| 24 | XAGUSD | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 534 | 89 | $53,462.00 | $-45,142.50 | 1.18 |
| 25 | XAGUSD | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 534 | 89 | $55,437.25 | $-48,307.50 | 1.15 |
| 26 | XAGUSD | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 623 | 89 | $69,490.00 | $-71,553.50 | 0.97 |
| 27 | XAGUSD | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 712 | 89 | $66,515.00 | $-71,161.00 | 0.93 |
| 28 | XAGUSD | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 356 | 89 | $33,257.50 | $-35,580.50 | 0.93 |
| 29 | XAGUSD | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 177 | 59 | $54,134.00 | $-58,675.00 | 0.92 |
| 30 | XAGUSD | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 413 | 59 | $75,704.50 | $-111,403.50 | 0.68 |
| 31 | XAGUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 267 | 89 | $23,155.25 | $-34,844.50 | 0.66 |
| 32 | XAGUSD | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 801 | 89 | $69,465.75 | $-104,533.50 | 0.66 |
| 33 | XAGUSD | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 534 | 89 | $46,310.50 | $-69,689.00 | 0.66 |
| 34 | XAGUSD | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 623 | 89 | $45,310.75 | $-80,551.50 | 0.56 |
| 35 | XAGUSD | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 623 | 89 | $49,261.25 | $-103,061.50 | 0.48 |
| 36 | XAGUSD | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 712 | 89 | $48,261.50 | $-113,924.00 | 0.42 |
| 37 | XAGUSD | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 623 | 89 | $38,159.25 | $-113,188.00 | 0.34 |
| 38 | XAGUSD | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 445 | 89 | $25,106.25 | $-79,079.50 | 0.32 |
| 39 | AUDJPY | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 441 | 63 | ¥-6,295,787 (~$-57,234) | ¥-22,659,354 (~$-205,994) | -0.28 |
| 40 | AUDJPY | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 189 | 63 | ¥-5,119,573 (~$-46,542) | ¥-13,867,291 (~$-126,066) | -0.37 |
| 41 | AUDJPY | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 574 | 82 | ¥-12,946,618 (~$-117,697) | ¥-32,589,438 (~$-296,268) | -0.40 |
| 42 | AUDJPY | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 246 | 82 | ¥-9,269,547 (~$-84,269) | ¥-18,826,527 (~$-171,150) | -0.49 |
| 43 | AUDJPY | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 876 | 146 | ¥-11,619,332 (~$-105,630) | ¥-22,727,442 (~$-206,613) | -0.51 |
| 44 | AUDJPY | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 1168 | 146 | ¥-16,556,801 (~$-150,516) | ¥-30,754,456 (~$-279,586) | -0.54 |
| 45 | AUDJPY | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 1022 | 146 | ¥-16,123,954 (~$-146,581) | ¥-27,604,543 (~$-250,950) | -0.58 |
| 46 | AUDJPY | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 876 | 146 | ¥-15,691,107 (~$-142,646) | ¥-24,534,969 (~$-223,045) | -0.64 |
| 47 | AUDJPY | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 1168 | 146 | ¥-21,507,276 (~$-195,521) | ¥-32,713,292 (~$-297,394) | -0.66 |
| 48 | AUDJPY | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 584 | 146 | ¥-10,753,638 (~$-97,760) | ¥-16,356,646 (~$-148,697) | -0.66 |
| 49 | AUDJPY | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 1022 | 146 | ¥-21,953,129 (~$-199,574) | ¥-30,163,306 (~$-274,212) | -0.73 |
| 50 | AUDJPY | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 1022 | 146 | ¥-24,267,504 (~$-220,614) | ¥-31,997,281 (~$-290,884) | -0.76 |
| 51 | AUDJPY | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 1314 | 146 | ¥-30,962,373 (~$-281,476) | ¥-40,753,572 (~$-370,487) | -0.76 |
| 52 | AUDJPY | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 876 | 146 | ¥-20,641,582 (~$-187,651) | ¥-27,169,048 (~$-246,991) | -0.76 |
| 53 | AUDJPY | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 438 | 146 | ¥-10,320,791 (~$-93,825) | ¥-13,584,524 (~$-123,496) | -0.76 |
| 54 | AUDJPY | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 1168 | 146 | ¥-31,408,226 (~$-285,529) | ¥-39,760,138 (~$-361,456) | -0.79 |
| 55 | AUDJPY | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 730 | 146 | ¥-21,087,435 (~$-191,704) | ¥-26,448,021 (~$-240,437) | -0.80 |
| 56 | AUDJPY | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 1022 | 146 | ¥-30,096,679 (~$-273,606) | ¥-37,740,711 (~$-343,097) | -0.80 |
| 57 | AUDJPY | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 1022 | 146 | ¥-30,975,379 (~$-281,594) | ¥-38,662,318 (~$-351,476) | -0.80 |

## Per-Market Ranking

### AUDJPY

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | ¥-6,295,787 | ¥-22,659,354 | -0.28 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | ¥-5,119,573 | ¥-13,867,291 | -0.37 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | ¥-12,946,618 | ¥-32,589,438 | -0.40 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | ¥-9,269,547 | ¥-18,826,527 | -0.49 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | ¥-11,619,332 | ¥-22,727,442 | -0.51 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | ¥-16,556,801 | ¥-30,754,456 | -0.54 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | ¥-16,123,954 | ¥-27,604,543 | -0.58 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | ¥-15,691,107 | ¥-24,534,969 | -0.64 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | ¥-21,507,276 | ¥-32,713,292 | -0.66 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | ¥-10,753,638 | ¥-16,356,646 | -0.66 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | ¥-21,953,129 | ¥-30,163,306 | -0.73 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | ¥-24,267,504 | ¥-31,997,281 | -0.76 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | ¥-30,962,373 | ¥-40,753,572 | -0.76 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | ¥-20,641,582 | ¥-27,169,048 | -0.76 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | ¥-10,320,791 | ¥-13,584,524 | -0.76 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | ¥-31,408,226 | ¥-39,760,138 | -0.79 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | ¥-21,087,435 | ¥-26,448,021 | -0.80 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | ¥-30,096,679 | ¥-37,740,711 | -0.80 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | ¥-30,975,379 | ¥-38,662,318 | -0.80 |

### XAGUSD

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $62,674.75 | $-41,246.50 | 1.52 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $100,563.50 | $-68,013.50 | 1.48 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $75,641.75 | $-56,814.50 | 1.33 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $65,539.50 | $-50,978.50 | 1.29 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $53,462.00 | $-45,142.50 | 1.18 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $55,437.25 | $-48,307.50 | 1.15 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $69,490.00 | $-71,553.50 | 0.97 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $66,515.00 | $-71,161.00 | 0.93 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $33,257.50 | $-35,580.50 | 0.93 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $54,134.00 | $-58,675.00 | 0.92 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $75,704.50 | $-111,403.50 | 0.68 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $23,155.25 | $-34,844.50 | 0.66 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $69,465.75 | $-104,533.50 | 0.66 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $46,310.50 | $-69,689.00 | 0.66 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $45,310.75 | $-80,551.50 | 0.56 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $49,261.25 | $-103,061.50 | 0.48 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $48,261.50 | $-113,924.00 | 0.42 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $38,159.25 | $-113,188.00 | 0.34 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $25,106.25 | $-79,079.50 | 0.32 |

### XAUUSD

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $521,978.40 | $-166,134.00 | 3.14 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $310,750.18 | $-105,716.07 | 2.94 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $327,473.55 | $-124,943.40 | 2.62 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $512,919.65 | $-242,113.62 | 2.12 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $715,368.75 | $-342,106.12 | 2.09 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $540,115.95 | $-258,960.27 | 2.09 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $728,966.90 | $-350,529.45 | 2.08 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $508,530.90 | $-246,594.20 | 2.06 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $620,945.45 | $-308,400.82 | 2.01 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $432,094.50 | $-216,831.65 | 1.99 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $216,047.25 | $-108,415.82 | 1.99 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $648,141.75 | $-325,247.47 | 1.99 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $229,645.40 | $-116,839.15 | 1.97 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $459,290.80 | $-233,678.30 | 1.97 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $256,841.70 | $-136,718.50 | 1.88 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $297,256.45 | $-158,406.07 | 1.88 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $310,854.60 | $-166,935.80 | 1.86 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $324,452.75 | $-177,580.45 | 1.83 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $391,684.10 | $-216,269.95 | 1.81 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| AUDJPY | limit_retest 4/2/1 + 20% range-close | 4/2/1 | ¥-6,295,787 | ¥-22,659,354 | -0.28 | +0.48 N/S |
| XAGUSD | limit_retest 1/1/1 + 20% range-close | 1/1/1 | $62,674.75 | $-41,246.50 | 1.52 | +0.85 N/S |
| XAUUSD | limit_retest 4/2/1 + 20% range-close | 4/2/1 | $521,978.40 | $-166,134.00 | 3.14 | +1.15 N/S |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.

## Causality note

Range-close / year-change market exits now set `live_after_ts=decision_bar.ts`, so PaperBroker fills on the **next daily open** (not the completed bar's open).

XAUUSD daily `2004-04-30` had corrupt `open=0/low=0`; repaired from clean 1m aggregate to `O 386.934 / H 390.345 / L 385.409 / C 386.136` (backup: `fx/xauusd_daily.csv.bak_pre_2004_04_30_repair`). Example L_4_2_1 campaign: short 7 @ 386.999 on 2004-04-29 → close 7 @ 386.944 on 2004-04-30 (next open + 1 tick) — scratch, not the old same-bar-open +$2k win.

Stance: **not promotion-safe**. Prior FX/metals yearly ORB sweep N/S was inflated by same-bar-open close lookahead; AUDJPY flips negative under causal fills.
