# NQ Monthly ORB Daily-Close Breakout Scaleout4

Rules:

- Monthly OR = first 3 daily rows in each calendar month.
- Entry = first daily close outside the range, filled at that same close.
- Skip if the breakout close is already beyond TP1.
- Four units: 1 exits halfway to TP1, 2 exit at TP1, 1 exits at TP2.
- Before TP1, any daily close back inside the OR exits all open units at that close.
- After TP1, the remaining runner stop moves to the breakout-side OR boundary.
- Same-bar ambiguity after TP1 is conservative: boundary stop is checked before TP2.

Dollar figures use NQ point value of $20/point per contract.

## Comparison

| Variant | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily restricted boundary entry | 325 | 27,897.0 | $557,940 | $-23,955 | 50.5% | 3.56 | n/a | n/a |
| Daily restricted scaleout3 boundary entry | 313 | 66,154.6 | $1,323,092 | $-34,160 | 64.9% | 4.67 | 75.7 | 1,038.0 |
| Daily close breakout scaleout4 50/TP1/TP2 | 181 | 11,557.4 | $231,148 | $-195,698 | 51.4% | 1.30 | 134.0 | 1,903.5 |

## Direction Split

| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Long | 111 | 11,999.9 | $239,998 | $-120,548 | 51.4% | 1.59 |
| Short | 70 | -442.5 | $-8,850 | $-216,485 | 51.4% | 0.98 |

## Exit Mix

- Daily-Close-Back-In-Range-Before-TP1: **67**
- TP50+TP1+Boundary-Stop-After-TP1: **42**
- TP50+TP1+TP2: **36**
- TP50+Daily-Close-Back-In-Range-Before-TP1: **18**
- TP50+TP1+Period-Close: **13**
- TP50+Period-Close: **4**
- Period-Close: **1**

## Skips

- Breakout close already beyond TP1: **9**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 7 | 432.8 | 4 | 3 | 21.1 | 35.2 |
| 2011 | 12 | 388.5 | 6 | 6 | 29.9 | 69.2 |
| 2012 | 10 | 557.5 | 5 | 5 | 19.6 | 57.0 |
| 2013 | 11 | 68.0 | 5 | 6 | 33.0 | 51.2 |
| 2014 | 12 | 1,044.9 | 8 | 4 | 31.0 | 70.5 |
| 2015 | 12 | 404.4 | 7 | 5 | 58.8 | 105.8 |
| 2016 | 11 | 932.9 | 5 | 6 | 47.4 | 140.2 |
| 2017 | 11 | 1,148.9 | 7 | 4 | 48.1 | 106.8 |
| 2018 | 11 | 1,165.4 | 6 | 5 | 107.8 | 267.0 |
| 2019 | 11 | 3,069.4 | 6 | 5 | 95.8 | 511.2 |
| 2020 | 11 | 6,923.6 | 8 | 3 | 163.2 | 324.0 |
| 2021 | 12 | -2,430.1 | 4 | 8 | 161.6 | 291.0 |
| 2022 | 12 | -1,330.8 | 6 | 6 | 249.4 | 806.8 |
| 2023 | 12 | 2,588.5 | 6 | 6 | 164.4 | 326.5 |
| 2024 | 11 | -5,869.0 | 3 | 8 | 326.8 | 916.0 |
| 2025 | 12 | 1,783.2 | 6 | 6 | 476.6 | 1903.5 |
| 2026 | 3 | 679.4 | 1 | 2 | 270.0 | 399.2 |

## Outputs

- `nq/nq_monthly_orb_daily_close_scaleout4.csv`
- `nq/nq_monthly_orb_daily_close_scaleout4_skips.csv`
