# Structure overnight gap fade

Fade gaps away from the active **bias-change 1h candle** H/L range.
Gap filters: yesterday-last vs today-first 1h **no price overlap**, gap ≥ **1/5**
of bias-candle range.
3ct: 1@+50 · 1@range boundary→BE · 1 runner@20R; first two EOD-only.
Re-entry at first-hour midpoint if price closes further away.

## Results

| metric | value |
|---|---|
| trades | 643 |
| net $ | -2392094 |
| win% | 16.3 |
| PF | 0.204 |
| avg $/trade | -3720.2 |
| long / short | 213 / 430 |
| reentries | 395 |
| hit_50 / boundary | 138 / 34 |

### By exit reason

| exit_reason                  |   count |              sum |     mean |
|:-----------------------------|--------:|-----------------:|---------:|
| boundary+be_stop             |       1 |    221           |   221    |
| eod                          |      22 | -50455.5         | -2293.43 |
| risk_stop                    |     482 |     -2.86893e+06 | -5952.14 |
| scale_50+boundary+be_stop    |      29 |  91049           |  3139.62 |
| scale_50+boundary+runner_20R |       4 | 148554           | 37138.5  |
| scale_50+eod                 |      85 | 338160           |  3978.35 |
| scale_50+risk_stop           |      20 | -50690           | -2534.5  |

### By year

|   year |   count |     sum |     mean |
|-------:|--------:|--------:|---------:|
|   2020 |      93 | -303557 | -3264.05 |
|   2021 |      70 | -148982 | -2128.32 |
|   2022 |     115 | -531488 | -4621.63 |
|   2023 |      82 | -180828 | -2205.22 |
|   2024 |     138 | -510282 | -3697.7  |
|   2025 |      93 | -390582 | -4199.81 |
|   2026 |      52 | -326376 | -6276.45 |
