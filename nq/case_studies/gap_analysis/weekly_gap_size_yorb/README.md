# NQ Weekly Gap Size + Yearly ORB Alignment Study

Definitions:

- Small / medium / big are empirical terciles of this market's weekly absolute gap size.
- Open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly ORB and the gap direction matches that side.
- Prior-close alignment: the previous RTH close was already outside the Jan-Mar yearly ORB and the gap direction matches that side.
- Fill means price traded back to the previous week's final RTH close before the end of that same week.

## Size Thresholds

| Bucket | Absolute Gap | Percent Of Prior Close |
|---|---:|---:|
| Small | <= 10.75 pts | <= 0.203% |
| Medium | > 10.75 and <= 41.00 pts | > 0.203% and <= 0.546% |
| Big | > 41.00 pts | > 0.546% |

## Fill Rate By Gap Size

| point_size_bucket | gaps | filled | not_filled | fill_rate | median_gap_pts | avg_gap_pts | max_gap_pts |
|---|---|---|---|---|---|---|---|
| Big | 270 | 186 | 84 | 68.9% | 93.00 | 134.57 | 999.25 |
| Medium | 274 | 217 | 57 | 79.2% | 23.00 | 23.26 | 41.00 |
| Small | 273 | 258 | 15 | 94.5% | 4.75 | 5.07 | 10.75 |

## Fill Rate By Gap Size And Direction

| point_size_bucket | direction | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|---|
| Big | Gap Down | 115 | 89 | 26 | 77.4% | 96.25 |
| Big | Gap Up | 155 | 97 | 58 | 62.6% | 87.25 |
| Medium | Gap Down | 119 | 102 | 17 | 85.7% | 23.00 |
| Medium | Gap Up | 155 | 115 | 40 | 74.2% | 23.00 |
| Small | Gap Down | 121 | 115 | 6 | 95.0% | 4.75 |
| Small | Gap Up | 152 | 143 | 9 | 94.1% | 4.88 |

## Yearly ORB Alignment At Weekly Open

| open_yorb_alignment | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|
| Aligned | 240 | 182 | 58 | 75.8% | 29.25 |
| Counter | 152 | 131 | 21 | 86.2% | 22.12 |
| Inside | 196 | 152 | 44 | 77.6% | 21.12 |
| NoRange | 38 | 34 | 4 | 89.5% | 8.38 |
| PreORB | 191 | 162 | 29 | 84.8% | 23.00 |

## Yearly ORB Alignment By Size

| open_yorb_alignment | point_size_bucket | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|---|
| Aligned | Big | 96 | 59 | 37 | 61.5% | 93.88 |
| Aligned | Medium | 82 | 64 | 18 | 78.0% | 23.62 |
| Aligned | Small | 62 | 59 | 3 | 95.2% | 4.75 |
| Counter | Big | 51 | 41 | 10 | 80.4% | 67.50 |
| Counter | Medium | 45 | 37 | 8 | 82.2% | 22.50 |
| Counter | Small | 56 | 53 | 3 | 94.6% | 5.00 |
| Inside | Big | 54 | 34 | 20 | 63.0% | 84.75 |
| Inside | Medium | 75 | 56 | 19 | 74.7% | 23.00 |
| Inside | Small | 67 | 62 | 5 | 92.5% | 5.00 |
| NoRange | Big | 7 | 6 | 1 | 85.7% | 187.00 |
| NoRange | Medium | 8 | 6 | 2 | 75.0% | 16.00 |
| NoRange | Small | 23 | 22 | 1 | 95.7% | 5.00 |
| PreORB | Big | 62 | 46 | 16 | 74.2% | 114.12 |
| PreORB | Medium | 64 | 54 | 10 | 84.4% | 23.50 |
| PreORB | Small | 65 | 62 | 3 | 95.4% | 4.50 |

## Stricter Prior-Close Alignment

| prev_close_yorb_alignment | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|
| Aligned | 231 | 175 | 56 | 75.8% | 29.00 |
| Counter | 161 | 138 | 23 | 85.7% | 22.50 |
| Inside | 196 | 152 | 44 | 77.6% | 21.12 |
| NoRange | 38 | 34 | 4 | 89.5% | 8.38 |
| PreORB | 191 | 162 | 29 | 84.8% | 23.00 |

## Unfilled Open-Aligned Gaps

Open-aligned weekly gaps that did not fill: **58**.

| open_date | direction | point_size_bucket | gap_pts | abs_gap_pts | prev_close | open_px | open_yorb_state | chart |
|---|---|---|---|---|---|---|---|---|
| 2025-10-13 | Gap Up | Big | 422.50 | 422.50 | 24402.250 | 24824.750 | Bullish | weekly_gap_4h/2025/2025-10-13_up_open_4h.png |
| 2022-06-13 | Gap Down | Big | -342.25 | 342.25 | 11837.000 | 11494.750 | Bearish | weekly_gap_4h/2022/2022-06-13_down_open_4h.png |
| 2023-09-11 | Gap Up | Big | 323.50 | 323.50 | 15295.250 | 15618.750 | Bullish | weekly_gap_4h/2023/2023-09-11_up_open_4h.png |
| 2025-09-15 | Gap Up | Big | 308.25 | 308.25 | 24110.250 | 24418.500 | Bullish | weekly_gap_4h/2025/2025-09-15_up_open_4h.png |
| 2025-10-27 | Gap Up | Big | 306.25 | 306.25 | 25509.500 | 25815.750 | Bullish | weekly_gap_4h/2025/2025-10-27_up_open_4h.png |
| 2024-06-17 | Gap Up | Big | 270.50 | 270.50 | 19687.500 | 19958.000 | Bullish | weekly_gap_4h/2024/2024-06-17_up_open_4h.png |
| 2023-06-12 | Gap Up | Big | 247.50 | 247.50 | 14556.500 | 14804.000 | Bullish | weekly_gap_4h/2023/2023-06-12_up_open_4h.png |
| 2022-05-09 | Gap Down | Big | -244.00 | 244.00 | 12693.250 | 12449.250 | Bearish | weekly_gap_4h/2022/2022-05-09_down_open_4h.png |
| 2025-08-04 | Gap Up | Big | 213.50 | 213.50 | 22880.500 | 23094.000 | Bullish | weekly_gap_4h/2025/2025-08-04_up_open_4h.png |
| 2025-11-24 | Gap Up | Big | 208.50 | 208.50 | 24313.750 | 24522.250 | Bullish | weekly_gap_4h/2025/2025-11-24_up_open_4h.png |
| 2020-09-28 | Gap Up | Big | 207.50 | 207.50 | 11133.250 | 11340.750 | Bullish | weekly_gap_4h/2020/2020-09-28_up_open_4h.png |
| 2020-10-12 | Gap Up | Big | 200.25 | 200.25 | 11711.500 | 11911.750 | Bullish | weekly_gap_4h/2020/2020-10-12_up_open_4h.png |
| 2025-12-22 | Gap Up | Big | 200.00 | 200.00 | 25580.750 | 25780.750 | Bullish | weekly_gap_4h/2025/2025-12-22_up_open_4h.png |
| 2023-12-11 | Gap Up | Big | 191.50 | 191.50 | 16098.750 | 16290.250 | Bullish | weekly_gap_4h/2023/2023-12-11_up_open_4h.png |
| 2019-07-01 | Gap Up | Big | 144.75 | 144.75 | 7693.750 | 7838.500 | Bullish | weekly_gap_4h/2019/2019-07-01_up_open_4h.png |
| 2020-07-06 | Gap Up | Big | 144.50 | 144.50 | 10326.000 | 10470.500 | Bullish | weekly_gap_4h/2020/2020-07-06_up_open_4h.png |
| 2024-09-16 | Gap Up | Big | 143.50 | 143.50 | 19527.250 | 19670.750 | Bullish | weekly_gap_4h/2024/2024-09-16_up_open_4h.png |
| 2023-08-28 | Gap Up | Big | 120.00 | 120.00 | 14977.500 | 15097.500 | Bullish | weekly_gap_4h/2023/2023-08-28_up_open_4h.png |
| 2020-12-28 | Gap Up | Big | 113.25 | 113.25 | 12703.000 | 12816.250 | Bullish | weekly_gap_4h/2020/2020-12-28_up_open_4h.png |
| 2022-07-11 | Gap Down | Big | -105.25 | 105.25 | 12155.500 | 12050.250 | Bearish | weekly_gap_4h/2022/2022-07-11_down_open_4h.png |
| 2023-10-30 | Gap Up | Big | 99.75 | 99.75 | 14266.000 | 14365.750 | Bullish | weekly_gap_4h/2023/2023-10-30_up_open_4h.png |
| 2022-12-05 | Gap Down | Big | -93.75 | 93.75 | 12013.750 | 11920.000 | Bearish | weekly_gap_4h/2022/2022-12-05_down_open_4h.png |
| 2025-09-08 | Gap Up | Big | 93.25 | 93.25 | 23691.000 | 23784.250 | Bullish | weekly_gap_4h/2025/2025-09-08_up_open_4h.png |
| 2020-08-03 | Gap Up | Big | 89.50 | 89.50 | 10897.750 | 10987.250 | Bullish | weekly_gap_4h/2020/2020-08-03_up_open_4h.png |
| 2019-08-26 | Gap Up | Big | 82.00 | 82.00 | 7473.750 | 7555.750 | Bullish | weekly_gap_4h/2019/2019-08-26_up_open_4h.png |

_Showing largest 25 of 58. See CSV for all rows._

## Files

- `weekly_gap_size_yorb.csv`
- `README.md`
- Big filled 1h charts: `../big_filled_weekly_gap_1h/README.md`
- Big unfilled 1h charts: `../big_unfilled_weekly_gap_1h/README.md`
- Main live-test candidate: `../weekly_gap_live_candidate_short_delivery_half3_tp1/README.md`
- Candidate winner/loser charts: `../weekly_gap_live_candidate_short_delivery_half3_tp1/charts/INDEX.md`
- Big gap-fill strategy pass: `../weekly_gap_fill_strategy_big/README.md`
- Big gap delivery-change strategy pass: `../weekly_gap_delivery_change_strategy_big/README.md`
- Big gap break-close 3 halfway / 2 TP1 pass: `../weekly_gap_delivery_break_close_half3_tp1_2/README.md`
