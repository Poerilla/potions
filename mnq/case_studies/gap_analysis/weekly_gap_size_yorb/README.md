# MNQ Weekly Gap Size + Yearly ORB Alignment Study

Definitions:

- Small / medium / big are empirical terciles of this market's weekly absolute gap size.
- Open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly ORB and the gap direction matches that side.
- Prior-close alignment: the previous RTH close was already outside the Jan-Mar yearly ORB and the gap direction matches that side.
- Fill means price traded back to the previous week's final RTH close before the end of that same week.

## Size Thresholds

| Bucket | Absolute Gap | Percent Of Prior Close |
|---|---:|---:|
| Small | <= 38.25 pts | <= 0.256% |
| Medium | > 38.25 and <= 103.17 pts | > 0.256% and <= 0.732% |
| Big | > 103.17 pts | > 0.732% |

## Fill Rate By Gap Size

| point_size_bucket | gaps | filled | not_filled | fill_rate | median_gap_pts | avg_gap_pts | max_gap_pts |
|---|---|---|---|---|---|---|---|
| Big | 121 | 77 | 44 | 63.6% | 186.75 | 226.38 | 998.75 |
| Medium | 119 | 95 | 24 | 79.8% | 58.50 | 63.79 | 102.00 |
| Small | 122 | 114 | 8 | 93.4% | 18.00 | 18.02 | 38.25 |

## Fill Rate By Gap Size And Direction

| point_size_bucket | direction | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|---|
| Big | Gap Down | 54 | 37 | 17 | 68.5% | 184.88 |
| Big | Gap Up | 67 | 40 | 27 | 59.7% | 187.75 |
| Medium | Gap Down | 46 | 43 | 3 | 93.5% | 59.00 |
| Medium | Gap Up | 73 | 52 | 21 | 71.2% | 58.25 |
| Small | Gap Down | 58 | 55 | 3 | 94.8% | 15.62 |
| Small | Gap Up | 64 | 59 | 5 | 92.2% | 19.62 |

## Yearly ORB Alignment At Weekly Open

| open_yorb_alignment | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|
| Aligned | 116 | 83 | 33 | 71.6% | 71.12 |
| Counter | 67 | 59 | 8 | 88.1% | 50.75 |
| Inside | 51 | 40 | 11 | 78.4% | 72.75 |
| NoRange | 50 | 38 | 12 | 76.0% | 43.50 |
| PreORB | 78 | 66 | 12 | 84.6% | 66.88 |

## Yearly ORB Alignment By Size

| open_yorb_alignment | point_size_bucket | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|---|
| Aligned | Big | 40 | 21 | 19 | 52.5% | 196.88 |
| Aligned | Medium | 45 | 33 | 12 | 73.3% | 65.25 |
| Aligned | Small | 31 | 29 | 2 | 93.5% | 19.50 |
| Counter | Big | 18 | 13 | 5 | 72.2% | 159.50 |
| Counter | Medium | 23 | 20 | 3 | 87.0% | 58.50 |
| Counter | Small | 26 | 26 | 0 | 100.0% | 11.25 |
| Inside | Big | 18 | 10 | 8 | 55.6% | 176.75 |
| Inside | Medium | 16 | 13 | 3 | 81.2% | 71.88 |
| Inside | Small | 17 | 17 | 0 | 100.0% | 22.75 |
| NoRange | Big | 14 | 11 | 3 | 78.6% | 198.25 |
| NoRange | Medium | 15 | 11 | 4 | 73.3% | 50.75 |
| NoRange | Small | 21 | 16 | 5 | 76.2% | 16.00 |
| PreORB | Big | 31 | 22 | 9 | 71.0% | 204.25 |
| PreORB | Medium | 20 | 18 | 2 | 90.0% | 57.12 |
| PreORB | Small | 27 | 26 | 1 | 96.3% | 19.50 |

## Stricter Prior-Close Alignment

| prev_close_yorb_alignment | gaps | filled | not_filled | fill_rate | median_gap_pts |
|---|---|---|---|---|---|
| Aligned | 113 | 80 | 33 | 70.8% | 69.75 |
| Counter | 70 | 62 | 8 | 88.6% | 48.75 |
| Inside | 51 | 40 | 11 | 78.4% | 74.00 |
| NoRange | 50 | 38 | 12 | 76.0% | 43.50 |
| PreORB | 78 | 66 | 12 | 84.6% | 66.88 |

## Unfilled Open-Aligned Gaps

Open-aligned weekly gaps that did not fill: **33**.

| open_date | direction | point_size_bucket | gap_pts | abs_gap_pts | prev_close | open_px | open_yorb_state | chart |
|---|---|---|---|---|---|---|---|---|
| 2025-10-13 | Gap Up | Big | 422.00 | 422.00 | 24402.750 | 24824.750 | Bullish | weekly_gap_4h/2025/2025-10-13_up_open_4h.png |
| 2022-06-13 | Gap Down | Big | -341.50 | 341.50 | 11837.250 | 11495.750 | Bearish | weekly_gap_4h/2022/2022-06-13_down_open_4h.png |
| 2023-09-11 | Gap Up | Big | 323.50 | 323.50 | 15295.250 | 15618.750 | Bullish | weekly_gap_4h/2023/2023-09-11_up_open_4h.png |
| 2025-09-15 | Gap Up | Big | 308.75 | 308.75 | 24109.500 | 24418.250 | Bullish | weekly_gap_4h/2025/2025-09-15_up_open_4h.png |
| 2025-10-27 | Gap Up | Big | 306.75 | 306.75 | 25509.000 | 25815.750 | Bullish | weekly_gap_4h/2025/2025-10-27_up_open_4h.png |
| 2024-06-17 | Gap Up | Big | 270.50 | 270.50 | 19687.500 | 19958.000 | Bullish | weekly_gap_4h/2024/2024-06-17_up_open_4h.png |
| 2023-06-12 | Gap Up | Big | 247.75 | 247.75 | 14556.250 | 14804.000 | Bullish | weekly_gap_4h/2023/2023-06-12_up_open_4h.png |
| 2022-05-09 | Gap Down | Big | -244.25 | 244.25 | 12693.000 | 12448.750 | Bearish | weekly_gap_4h/2022/2022-05-09_down_open_4h.png |
| 2025-08-04 | Gap Up | Big | 213.50 | 213.50 | 22880.750 | 23094.250 | Bullish | weekly_gap_4h/2025/2025-08-04_up_open_4h.png |
| 2025-11-24 | Gap Up | Big | 208.50 | 208.50 | 24313.750 | 24522.250 | Bullish | weekly_gap_4h/2025/2025-11-24_up_open_4h.png |
| 2020-09-28 | Gap Up | Big | 208.00 | 208.00 | 11133.500 | 11341.500 | Bullish | weekly_gap_4h/2020/2020-09-28_up_open_4h.png |
| 2020-10-12 | Gap Up | Big | 201.00 | 201.00 | 11711.500 | 11912.500 | Bullish | weekly_gap_4h/2020/2020-10-12_up_open_4h.png |
| 2025-12-22 | Gap Up | Big | 199.25 | 199.25 | 25581.250 | 25780.500 | Bullish | weekly_gap_4h/2025/2025-12-22_up_open_4h.png |
| 2023-12-11 | Gap Up | Big | 191.50 | 191.50 | 16098.500 | 16290.000 | Bullish | weekly_gap_4h/2023/2023-12-11_up_open_4h.png |
| 2020-07-06 | Gap Up | Big | 144.75 | 144.75 | 10325.250 | 10470.000 | Bullish | weekly_gap_4h/2020/2020-07-06_up_open_4h.png |
| 2024-09-16 | Gap Up | Big | 143.75 | 143.75 | 19527.250 | 19671.000 | Bullish | weekly_gap_4h/2024/2024-09-16_up_open_4h.png |
| 2023-08-28 | Gap Up | Big | 120.50 | 120.50 | 14977.750 | 15098.250 | Bullish | weekly_gap_4h/2023/2023-08-28_up_open_4h.png |
| 2020-12-28 | Gap Up | Big | 111.25 | 111.25 | 12704.750 | 12816.000 | Bullish | weekly_gap_4h/2020/2020-12-28_up_open_4h.png |
| 2022-07-11 | Gap Down | Big | -104.75 | 104.75 | 12155.250 | 12050.500 | Bearish | weekly_gap_4h/2022/2022-07-11_down_open_4h.png |
| 2023-10-30 | Gap Up | Medium | 99.00 | 99.00 | 14266.250 | 14365.250 | Bullish | weekly_gap_4h/2023/2023-10-30_up_open_4h.png |
| 2025-09-08 | Gap Up | Medium | 93.75 | 93.75 | 23690.500 | 23784.250 | Bullish | weekly_gap_4h/2025/2025-09-08_up_open_4h.png |
| 2022-12-05 | Gap Down | Medium | -92.25 | 92.25 | 12013.000 | 11920.750 | Bearish | weekly_gap_4h/2022/2022-12-05_down_open_4h.png |
| 2020-08-03 | Gap Up | Medium | 89.50 | 89.50 | 10897.500 | 10987.000 | Bullish | weekly_gap_4h/2020/2020-08-03_up_open_4h.png |
| 2020-07-27 | Gap Up | Medium | 77.25 | 77.25 | 10469.500 | 10546.750 | Bullish | weekly_gap_4h/2020/2020-07-27_up_open_4h.png |
| 2020-08-17 | Gap Up | Medium | 69.25 | 69.25 | 11159.500 | 11228.750 | Bullish | weekly_gap_4h/2020/2020-08-17_up_open_4h.png |

_Showing largest 25 of 33. See CSV for all rows._

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
