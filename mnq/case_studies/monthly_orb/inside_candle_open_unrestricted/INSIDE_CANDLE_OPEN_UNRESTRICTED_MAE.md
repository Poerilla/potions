# Inside-Candle-Open Unrestricted Winner MAE

Rows are profitable trades only. For longs, source extreme means the selected inside candle low. For shorts, source extreme means the selected inside candle high.

- `Normal_MAE_Pts`: adverse excursion from entry after fill, using daily OHLC.
- `Source_Cushion_Pts`: distance from entry open to selected source candle low/high.
- `MAE_Beyond_Source_Extreme_Pts`: amount price moved beyond the selected source candle low/high after fill. Zero means the selected source extreme held.

| Instrument | Group | Winners | Net | Avg normal MAE | Median normal MAE | Avg source cushion | Avg beyond source extreme | Median beyond | Max beyond | No source violation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | All | 29 | $30,785.50 | 92.02 | 48.50 | 140.19 | 23.62 | 0.00 | 180.75 | 58.6% |
| MNQ | Long | 16 | $13,696.00 | 110.69 | 44.25 | 147.97 | 35.42 | 0.00 | 180.75 | 56.2% |
| MNQ | Short | 13 | $17,089.50 | 69.04 | 54.00 | 130.62 | 9.10 | 0.00 | 38.75 | 61.5% |
| NQ | All | 68 | $365,005.00 | 54.66 | 26.75 | 81.61 | 13.86 | 0.00 | 181.50 | 61.8% |
| NQ | Long | 34 | $163,565.00 | 68.38 | 29.62 | 97.38 | 19.30 | 0.00 | 181.50 | 67.6% |
| NQ | Short | 34 | $201,440.00 | 40.94 | 25.00 | 65.85 | 8.41 | 0.00 | 50.75 | 55.9% |

Detail CSV: [inside_candle_open_unrestricted_mae.csv](inside_candle_open_unrestricted_mae.csv)
