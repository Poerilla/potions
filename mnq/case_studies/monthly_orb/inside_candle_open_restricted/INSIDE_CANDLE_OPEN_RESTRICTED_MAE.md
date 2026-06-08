# Inside-Candle-Open Restricted Winner MAE

Rows are profitable trades only. For longs, source extreme means the selected inside candle low. For shorts, source extreme means the selected inside candle high.

- `Normal_MAE_Pts`: adverse excursion from entry after fill, using daily OHLC.
- `Source_Cushion_Pts`: distance from entry open to selected source candle low/high.
- `MAE_Beyond_Source_Extreme_Pts`: amount price moved beyond the selected source candle low/high after fill. Zero means the selected source extreme held.

| Instrument | Group | Winners | Net | Avg normal MAE | Median normal MAE | Avg source cushion | Avg beyond source extreme | Median beyond | Max beyond | No source violation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | All | 42 | $19,476.00 | 60.38 | 44.38 | 168.59 | 3.61 | 0.00 | 82.25 | 88.1% |
| MNQ | Long | 27 | $7,868.50 | 64.48 | 39.25 | 178.60 | 3.64 | 0.00 | 82.25 | 88.9% |
| MNQ | Short | 15 | $11,607.50 | 53.00 | 48.00 | 150.57 | 3.57 | 0.00 | 38.75 | 86.7% |
| NQ | All | 86 | $224,655.00 | 33.97 | 15.00 | 98.18 | 2.50 | 0.00 | 81.25 | 84.9% |
| NQ | Long | 52 | $98,885.00 | 39.31 | 17.88 | 110.87 | 2.85 | 0.00 | 81.25 | 82.7% |
| NQ | Short | 34 | $125,770.00 | 25.82 | 7.00 | 78.78 | 1.96 | 0.00 | 39.25 | 88.2% |

Detail CSV: [inside_candle_open_restricted_mae.csv](inside_candle_open_restricted_mae.csv)
