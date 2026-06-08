# MNQ Monthly ORB Daily-Close Breakout Scaleout4

Rules:

- Monthly OR = first 3 daily rows in each calendar month.
- Entry = first daily close outside the range, filled at that same close.
- Skip if the breakout close is already beyond TP1.
- Four units: 1 exits halfway to TP1, 2 exit at TP1, 1 exits at TP2.
- Before TP1, any daily close back inside the OR exits all open units at that close.
- After TP1, the remaining runner stop moves to the breakout-side OR boundary.
- Same-bar ambiguity after TP1 is conservative: boundary stop is checked before TP2.

Dollar figures use MNQ point value of $2/point per contract.

## Comparison

| Variant | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily restricted boundary entry | 141 | 22,019.5 | $44,039 | $-2,394 | 50.4% | 3.58 | n/a | n/a |
| Daily restricted scaleout3 boundary entry | 139 | 52,577.0 | $105,154 | $-3,411 | 67.6% | 4.73 | 137.0 | 1,039.2 |
| 4h close restricted daily range-close | 162 | 3,617.8 | $7,236 | $-6,656 | 44.4% | 1.25 | 159.7 | 966.5 |
| 4h close restricted scaleout3 daily range-close | 151 | 6,044.7 | $12,089 | $-11,732 | 43.0% | 1.18 | 181.3 | 829.0 |
| 4h swing-stop single, re-armed | 131 | 3,939.4 | $7,879 | $-8,336 | 46.6% | 1.21 | 228.4 | 1,831.8 |
| 4h swing-stop scaleout3, re-armed | 131 | 8,445.6 | $16,891 | $-15,093 | 46.6% | 1.21 | 241.4 | 1,831.8 |
| Daily close breakout scaleout4 50/TP1/TP2 | 80 | 5,572.1 | $11,144 | $-19,777 | 47.5% | 1.18 | 240.1 | 1,901.8 |

## Direction Split

| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Long | 52 | 5,738.6 | $11,477 | $-12,068 | 46.2% | 1.35 |
| Short | 28 | -166.5 | $-333 | $-21,623 | 50.0% | 0.99 |

## Exit Mix

- Daily-Close-Back-In-Range-Before-TP1: **31**
- TP50+TP1+Boundary-Stop-After-TP1: **16**
- TP50+TP1+TP2: **16**
- TP50+Daily-Close-Back-In-Range-Before-TP1: **11**
- TP50+TP1+Period-Close: **5**
- TP50+Period-Close: **1**

## Skips

- Breakout close already beyond TP1: **3**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 7 | 3,486.9 | 5 | 2 | 54.9 | 121.8 |
| 2020 | 11 | 6,754.5 | 8 | 3 | 162.8 | 324.0 |
| 2021 | 12 | -2,527.4 | 3 | 9 | 162.5 | 290.8 |
| 2022 | 12 | -1,350.8 | 6 | 6 | 249.4 | 808.0 |
| 2023 | 12 | 2,600.5 | 6 | 6 | 164.6 | 326.8 |
| 2024 | 11 | -5,871.0 | 3 | 8 | 326.4 | 916.0 |
| 2025 | 12 | 1,796.4 | 6 | 6 | 476.6 | 1901.8 |
| 2026 | 3 | 683.0 | 1 | 2 | 269.0 | 397.8 |

## Outputs

- `mnq/mnq_monthly_orb_daily_close_scaleout4.csv`
- `mnq/mnq_monthly_orb_daily_close_scaleout4_skips.csv`
