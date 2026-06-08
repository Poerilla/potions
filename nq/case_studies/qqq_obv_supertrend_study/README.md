# QQQ OBV Crossover + Daily Supertrend Study

Data: Yahoo daily QQQ adjusted OHLCV. Fetch method in this run: `yahoo_chart_api`.
Window: **2000-01-03 through 2026-05-29**.

Rules:

- OBV uses adjusted close direction and raw Yahoo volume.
- OBV crossover means OBV crossing its `20`-day simple moving average.
- Daily Supertrend is `ATR(14) x 3.0` on adjusted OHLC.
- Equity rows are close-to-close research states with next-session execution, no costs, and no shorting.

## Equity State Summary

| State | End Capital on $10k | Net | CAGR | Max DD | Net/DD | Exposure |
|---|---:|---:|---:|---:|---:|---:|
| QQQ buy-and-hold | $92,373 | $82,373 | 8.79% | -82.96% | 9.93 | 100.0% |
| OBV > OBV_MA | $33,063 | $23,063 | 4.63% | -69.42% | 3.32 | 57.1% |
| Daily Supertrend bullish | $48,906 | $38,906 | 6.20% | -52.64% | 7.39 | 59.6% |
| OBV > OBV_MA and Supertrend bullish | $29,902 | $19,902 | 4.24% | -60.46% | 3.29 | 45.6% |

## Forward Return Summary

| Signal | ST Regime | Count | Avg 5d | Hit 5d | Avg 20d | Hit 20d | Avg 60d | Hit 60d |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| bearish_obv_cross | bearish_st | 189 | -0.47% | 53.4% | 0.36% | 56.6% | 0.65% | 56.6% |
| bearish_obv_cross | bullish_st | 270 | 0.40% | 57.8% | 0.50% | 56.5% | 1.81% | 65.4% |
| bullish_obv_cross | bearish_st | 237 | 0.07% | 56.5% | 0.65% | 61.2% | 1.06% | 61.9% |
| bullish_obv_cross | bullish_st | 223 | 0.17% | 57.8% | 0.03% | 57.7% | 1.27% | 64.4% |

## Charts

- [Recent indicator chart](charts/qqq_obv_supertrend_recent.png)
- [Full-history indicator chart](charts/qqq_obv_supertrend_full.png)

## Yearly Charts

| Year | Bars | Return | Bull Crosses | Bear Crosses | ST Bull % | Chart |
|---:|---:|---:|---:|---:|---:|---|
| 2000 | 252 | -38.4% | 15 | 15 | 42.9% | [charts/yearly/2000.png](charts/yearly/2000.png) |
| 2001 | 248 | -27.2% | 16 | 15 | 38.7% | [charts/yearly/2001.png](charts/yearly/2001.png) |
| 2002 | 252 | -39.2% | 25 | 26 | 39.3% | [charts/yearly/2002.png](charts/yearly/2002.png) |
| 2003 | 252 | 43.6% | 21 | 20 | 65.9% | [charts/yearly/2003.png](charts/yearly/2003.png) |
| 2004 | 252 | 10.8% | 14 | 15 | 62.3% | [charts/yearly/2004.png](charts/yearly/2004.png) |
| 2005 | 252 | 2.6% | 19 | 19 | 45.2% | [charts/yearly/2005.png](charts/yearly/2005.png) |
| 2006 | 251 | 4.8% | 16 | 16 | 50.2% | [charts/yearly/2006.png](charts/yearly/2006.png) |
| 2007 | 251 | 18.8% | 25 | 25 | 64.5% | [charts/yearly/2007.png](charts/yearly/2007.png) |
| 2008 | 253 | -40.8% | 19 | 19 | 28.1% | [charts/yearly/2008.png](charts/yearly/2008.png) |
| 2009 | 252 | 48.3% | 16 | 15 | 75.0% | [charts/yearly/2009.png](charts/yearly/2009.png) |
| 2010 | 252 | 18.4% | 11 | 11 | 58.3% | [charts/yearly/2010.png](charts/yearly/2010.png) |
| 2011 | 252 | 1.9% | 16 | 17 | 60.3% | [charts/yearly/2011.png](charts/yearly/2011.png) |
| 2012 | 250 | 15.9% | 10 | 10 | 65.2% | [charts/yearly/2012.png](charts/yearly/2012.png) |
| 2013 | 252 | 32.4% | 18 | 17 | 86.5% | [charts/yearly/2013.png](charts/yearly/2013.png) |
| 2014 | 252 | 20.1% | 14 | 14 | 67.5% | [charts/yearly/2014.png](charts/yearly/2014.png) |
| 2015 | 252 | 9.8% | 28 | 29 | 41.7% | [charts/yearly/2015.png](charts/yearly/2015.png) |
| 2016 | 252 | 9.4% | 16 | 16 | 67.9% | [charts/yearly/2016.png](charts/yearly/2016.png) |
| 2017 | 251 | 31.5% | 18 | 17 | 84.1% | [charts/yearly/2017.png](charts/yearly/2017.png) |
| 2018 | 251 | -1.8% | 19 | 20 | 42.6% | [charts/yearly/2018.png](charts/yearly/2018.png) |
| 2019 | 252 | 38.4% | 7 | 6 | 77.0% | [charts/yearly/2019.png](charts/yearly/2019.png) |
| 2020 | 253 | 46.0% | 16 | 16 | 73.1% | [charts/yearly/2020.png](charts/yearly/2020.png) |
| 2021 | 252 | 29.2% | 16 | 17 | 64.3% | [charts/yearly/2021.png](charts/yearly/2021.png) |
| 2022 | 251 | -33.2% | 26 | 26 | 27.9% | [charts/yearly/2022.png](charts/yearly/2022.png) |
| 2023 | 250 | 55.9% | 16 | 15 | 79.6% | [charts/yearly/2023.png](charts/yearly/2023.png) |
| 2024 | 252 | 27.7% | 14 | 15 | 75.4% | [charts/yearly/2024.png](charts/yearly/2024.png) |
| 2025 | 250 | 21.0% | 23 | 23 | 68.0% | [charts/yearly/2025.png](charts/yearly/2025.png) |
| 2026 | 102 | 20.6% | 6 | 5 | 57.8% | [charts/yearly/2026.png](charts/yearly/2026.png) |

## Files

- `QQQ_daily_obv_supertrend.csv`
- `signals.csv`
- `forward_return_summary.csv`
- `equity_summary.csv`
- `yearly_summary.csv`
