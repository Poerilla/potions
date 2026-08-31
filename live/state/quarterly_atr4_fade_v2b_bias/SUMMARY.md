# Quarterly ATR4 fade → v2b S_1_1_3 bias

v2b London S_1_1_3 arms **only** on sessions where the market's best-path
quarterly fade ladder trade is open, and **only** in that trade's direction.
CFDs (US30/NAS100) use full 1m history from 2017 (not the 2021 demo start).

| Market | Path | Path WR | Bias sess | Trades | Units | Net USD | Stress | N/S | WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| AUDJPY | second_after_lower | 36.4% | 5 | 3 | 15 | -853 | -1343 | -0.63 | 13.3% |
| EURUSD | second_after_upper | 41.2% | 54 | 52 | 260 | -9375 | -11317 | -0.83 | 15.0% |
| GBPUSD | first_lower | 58.5% | 413 | 388 | 1940 | -70523 | -77755 | -0.91 | 16.8% |
| NAS100 | first_lower | 55.6% | 129 | 116 | 580 | +90 | -2003 | 0.04 | 20.7% |
| US30 | first_lower | 72.7% | 24 | 21 | 105 | -2075 | -2715 | -0.76 | 14.3% |
| USDJPY | second_after_lower | 50.0% | 19 | 17 | 85 | -3920 | -6488 | -0.60 | 15.3% |
| XAGUSD | second_after_lower | 44.4% | 34 | 30 | 150 | -5465 | -5480 | -1.00 | 8.7% |
| XAUUSD | second_after_upper | 53.8% | 8 | 8 | 40 | -6034 | -6798 | -0.89 | 10.0% |

Hub: `live/state/quarterly_atr4_fade_v2b_bias`
Bias maps: `bias/<symbol>_fade_bias_by_session.csv`

**Stance:** fade-as-v2b-bias does **not** promote — only NAS100 is soft-positive; rest lose with low WR (~8–17%). Absolute loss is smaller than ungated London S_1_1_3 because the fade gate fires far fewer sessions, but alignment does not flip FX/metals/US30 into edge.
