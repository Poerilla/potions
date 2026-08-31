# Bias-candle OR OCO (1/1/2/1, 09:30 arm, trade-through)

Bias-change 1h candle = OR. OCO stops arm at **09:30** only. **No gap-through fills** — must trade through the boundary (reclaim+rebreak if gapped). Sizing **1/1/2/1**: 1@1R · 1@2R · 2@EOD · 1 runner@20R (stackable). **2 attempts** per bias candle.

## Results

| metric | value |
|---|---|
| trades | 379 |
| day / runner rows | 244 / 135 |
| net $ | -476320 |
| win% | 29.0 |
| PF | 0.707 |
| avg $/trade | -1256.8 |
| long / short | 192 / 187 |
| attempt 1 / 2 | 235 / 144 |
| hit_tp1 / tp2 | 190 / 24 |

### By kind

| kind   |   count |     sum |     mean |
|:-------|--------:|--------:|---------:|
| day    |     244 | -621330 | -2546.43 |
| runner |     135 |  145010 |  1074.15 |

### By exit reason

| exit_reason             |   count |     sum |      mean |
|:------------------------|--------:|--------:|----------:|
| eod+be_stop             |      92 | -332361 |  -3612.62 |
| eod+eod_residual        |       2 |      -6 |     -3    |
| eod+runner_20R          |       6 |  344682 |  57447    |
| eod+runner_spin         |     100 |  -70840 |   -708.4  |
| or_stop                 |      89 | -988635 | -11108.3  |
| tp1+be_stop             |      14 |   26235 |   1873.93 |
| tp1+eod+be_stop         |      25 |     -75 |     -3    |
| tp1+eod+runner_20R      |       1 |   54797 |  54797    |
| tp1+eod+runner_spin     |      26 |  261323 |  10050.9  |
| tp1+tp2+be_stop         |       6 |   22515 |   3752.5  |
| tp1+tp2+eod+be_stop     |       7 |     -21 |     -3    |
| tp1+tp2+eod+runner_20R  |       2 |   77994 |  38997    |
| tp1+tp2+eod+runner_spin |       9 |  128072 |  14230.2  |

### By year

|   year |   count |     sum |      mean |
|-------:|--------:|--------:|----------:|
|   2020 |      45 |  236295 |  5251     |
|   2021 |      79 |  -33235 |  -420.696 |
|   2022 |      38 |  -39915 | -1050.39  |
|   2023 |      71 | -105920 | -1491.83  |
|   2024 |      61 | -162540 | -2664.59  |
|   2025 |      56 | -175095 | -3126.7   |
|   2026 |      29 | -195910 | -6755.52  |

### By attempt

|   attempt |   count |     sum |      mean |
|----------:|--------:|--------:|----------:|
|         1 |     235 | -105855 |  -450.447 |
|         2 |     144 | -370465 | -2572.67  |

