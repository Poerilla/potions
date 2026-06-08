# MNQ Daily Candlestick Theory Study

Lookahead window for strategy: 20 bars after C3.

## Theory Summary

| Direction | Setups | Hits | Hit Rate | C3 Close Beyond | Close Rate | Avg Extension | Median Extension | Avg Adverse | Worst Adverse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bearish | 449 | 273 | 60.80% | 129 | 28.73% | 157.87 | 108.75 | 29.75 | 1234.00 |
| bullish | 687 | 521 | 75.84% | 288 | 41.92% | 101.30 | 69.50 | 32.59 | 895.25 |
| all | 1136 | 794 | 69.89% | 417 | 36.71% | 120.75 | 79.88 | 31.47 | 1234.00 |

## Strategy: Breakout-Candle Entry · TP = 2R

OC = C3 bar.  R = OC.high − OC.low.  Breakout: first bar in lookahead window that closes beyond OC.  Entry at breakout close.  SL = entry ± 2R.  TP = entry ± 2R.

| Direction | Setups | No Breakout | Resolved | open_window | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 687 | 98 | 459 | 130 | 242 | 217 | 52.72% | 0.893 | 282.89 | 3.9 | 6.8 | 4.7 | +50.00 | +7478.50 | 270 / 45.8% | 194 / 80.2% |
| bearish | 449 | 163 | 239 | 47 | 111 | 128 | 46.44% | 0.907 | 422.80 | 4.1 | 4.8 | 5.1 | -34.00 | -15931.50 | 145 / 50.7% | 76 / 68.5% |
| all | 1136 | 261 | 698 | 177 | 353 | 345 | 50.57% | 0.898 | 330.80 | 4.0 | 6.2 | 4.8 | +16.00 | -8453.00 | 415 / 47.4% | 270 / 76.5% |

## Strategy: Breakout-Candle Entry · TP = 3R

Same entry/SL rules.  TP = entry ± 3R.

| Direction | Setups | No Breakout | Resolved | open_window | TP | SL | Hit Rate | Avg MAE (R) | Avg MAE (pts) | Avg Breakout Day | Avg days→TP | Avg days→SL | Total PnL (R) | Total PnL (pts) | Swept Opposing (n/%) | Clean Body→TP (n/%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bullish | 687 | 98 | 394 | 195 | 152 | 242 | 38.58% | 1.055 | 322.26 | 3.9 | 7.4 | 5.0 | -28.00 | -16588.50 | 270 / 45.8% | 128 / 84.2% |
| bearish | 449 | 163 | 214 | 72 | 74 | 140 | 34.58% | 1.044 | 474.87 | 4.1 | 6.1 | 5.5 | -58.00 | -24114.25 | 145 / 50.7% | 52 / 70.3% |
| all | 1136 | 261 | 608 | 267 | 226 | 382 | 37.17% | 1.051 | 375.98 | 4.0 | 7.0 | 5.2 | -86.00 | -40702.75 | 415 / 47.4% | 180 / 79.6% |

## Skipped / Failure Sweep Context

- High failure sweeps: 509
- Low failure sweeps: 495
- Unique non-signal failure-sweep bars: 614
- Non-signal rolling windows: 994

CSV outputs: `setups.csv` · `summary.csv` · `strat_2r_trades.csv` · `strat_3r_trades.csv` · `strat_2r_summary.csv` · `strat_3r_summary.csv`
