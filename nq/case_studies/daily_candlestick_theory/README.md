# NQ Daily Candlestick Theory Study

Lookahead window for strategy: 20 bars after C3.

## Theory Summary

| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | Avg Extension | Median Extension | Avg Adverse | Worst Adverse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bearish | 990 | 605 | 61.11% | 280 | 28.28% | 88.63 | 39.50 | 17.48 | 1261.50 |
| bullish | 1535 | 1138 | 74.14% | 620 | 40.39% | 58.11 | 26.25 | 17.46 | 895.00 |
| all | 2525 | 1743 | 69.03% | 900 | 35.64% | 68.70 | 31.75 | 17.47 | 1261.50 |

## Strategy: Breakout-Candle Entry · TP = 2R

OC = C3 bar.  R = OC.high − OC.low.  Breakout: first bar in lookahead window that closes beyond OC.  Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.

| Direction | Setups | No Breakout | Resolved | open_window | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 1535 | 202 | 1048 | 285 | 549 | 499 | 52.39% | 0.914 | 157.87 | 4.1 | 6.3 | 5.0 | +100.00 | +6940.00 | 602 / 45.2% | 448 / 81.6% |
| bearish | 990 | 340 | 523 | 127 | 224 | 299 | 42.83% | 0.970 | 236.91 | 4.6 | 4.8 | 4.8 | -150.00 | -18560.00 | 329 / 50.6% | 154 / 68.8% |
| all | 2525 | 542 | 1571 | 412 | 773 | 798 | 49.20% | 0.933 | 184.19 | 4.2 | 5.9 | 4.9 | -50.00 | -11620.00 | 931 / 46.9% | 602 / 77.9% |

## Strategy: Breakout-Candle Entry · TP = 3R

Same entry/SL rules.  TP = entry ± 3R.

| Direction | Setups | No Breakout | Resolved | open_window | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 1535 | 202 | 920 | 413 | 368 | 552 | 40.00% | 1.062 | 177.71 | 4.1 | 7.3 | 5.3 | +0.00 | -22037.25 | 602 / 45.2% | 316 / 85.9% |
| bearish | 990 | 340 | 474 | 176 | 144 | 330 | 30.38% | 1.100 | 262.17 | 4.6 | 5.6 | 5.4 | -228.00 | -29297.25 | 329 / 50.6% | 106 / 73.6% |
| all | 2525 | 542 | 1394 | 589 | 512 | 882 | 36.73% | 1.075 | 206.43 | 4.2 | 6.8 | 5.3 | -228.00 | -51334.50 | 931 / 46.9% | 422 / 82.4% |

## Skipped / Failure Sweep Context

- High failure sweeps: 1209
- Low failure sweeps: 1173
- Unique non-signal failure-sweep bars: 1454
- Non-signal rolling windows: 2360

CSV outputs: `setups.csv` · `summary.csv` · `strat_2r_trades.csv` · `strat_3r_trades.csv` · `strat_2r_summary.csv` · `strat_3r_summary.csv`
