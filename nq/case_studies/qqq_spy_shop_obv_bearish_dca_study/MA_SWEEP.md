# QQQ / SPY / SHOP Slower OBV MA Sweep

Purpose: test slower OBV moving averages after the 20-day OBV bearish cross fired too often.

Method: each ticker contributes `$1,000` per month, then signal variants buy only when daily OBV crosses below the selected OBV SMA. The static add size is calibrated as `$12k / observed bearish crosses per year`; rolling variants use prior 1y/2y/3y/5y/10y signal frequency and cap buys at available cash.

Window: **2015-06-01 through 2026-06-01**. Tested OBV SMA lengths: **20, 50, 100, 150, 200, 252, 504**. Rolling lookbacks: **1, 2, 3, 5, 10 years**.

## Frequency Sweep

| Ticker | OBV SMA | Bear Crosses | Crosses / Year | Static Add | Best OBV Variant | Best OBV Ending Equity | vs Monthly DCA | Best OBV Max DD |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| QQQ | 20 | 189 | 17.18 | $698 | obv_bear_rolling_10y | $469,309 | $-7,181 | $-71,993 |
| QQQ | 50 | 103 | 9.36 | $1,282 | obv_bear_rolling_10y | $466,481 | $-10,009 | $-71,555 |
| QQQ | 100 | 85 | 7.73 | $1,553 | obv_bear_rolling_1y | $463,183 | $-13,306 | $-69,694 |
| QQQ | 150 | 59 | 5.36 | $2,237 | obv_bear_rolling_1y | $459,409 | $-17,081 | $-69,284 |
| QQQ | 200 | 61 | 5.55 | $2,164 | obv_bear_rolling_1y | $456,316 | $-20,174 | $-67,355 |
| QQQ | 252 | 41 | 3.73 | $3,220 | obv_bear_rolling_1y | $448,997 | $-27,493 | $-65,216 |
| QQQ | 504 | 9 | 0.82 | $14,668 | obv_bear_static_full_window | $367,912 | $-108,578 | $-52,494 |
| SHOP | 20 | 169 | 15.36 | $781 | obv_bear_rolling_10y | $1,238,524 | $-22,810 | $-1,306,562 |
| SHOP | 50 | 109 | 9.91 | $1,211 | obv_bear_rolling_10y | $1,237,969 | $-23,365 | $-1,296,718 |
| SHOP | 100 | 61 | 5.55 | $2,164 | obv_bear_rolling_10y | $1,228,864 | $-32,470 | $-1,306,300 |
| SHOP | 150 | 47 | 4.27 | $2,809 | obv_bear_rolling_10y | $1,059,614 | $-201,719 | $-1,100,534 |
| SHOP | 200 | 37 | 3.36 | $3,568 | obv_bear_rolling_3y | $619,278 | $-642,056 | $-544,758 |
| SHOP | 252 | 20 | 1.82 | $6,600 | obv_bear_rolling_3y | $593,097 | $-668,237 | $-517,974 |
| SHOP | 504 | 32 | 2.91 | $4,125 | obv_bear_rolling_3y | $630,906 | $-630,427 | $-567,883 |
| SPY | 20 | 202 | 18.36 | $654 | obv_bear_rolling_10y | $331,919 | $-5,296 | $-44,484 |
| SPY | 50 | 113 | 10.27 | $1,168 | obv_bear_rolling_10y | $332,445 | $-4,770 | $-45,027 |
| SPY | 100 | 76 | 6.91 | $1,737 | obv_bear_rolling_10y | $327,744 | $-9,471 | $-42,760 |
| SPY | 150 | 66 | 6.00 | $2,000 | obv_bear_rolling_10y | $332,363 | $-4,853 | $-44,178 |
| SPY | 200 | 47 | 4.27 | $2,809 | obv_bear_rolling_1y | $323,528 | $-13,687 | $-42,644 |
| SPY | 252 | 29 | 2.64 | $4,552 | obv_bear_rolling_1y | $314,839 | $-22,377 | $-39,201 |
| SPY | 504 | 19 | 1.73 | $6,948 | obv_bear_rolling_10y | $274,434 | $-62,781 | $-30,963 |

## Read

- **QQQ:** best OBV timing is SMA 20 (`obv_bear_rolling_10y`) at $469,309, versus monthly DCA at $476,490. It is $-7,181 relative to monthly.
  Rarest tested signal is SMA 504 at 0.82 crosses/year with a $14,668 static matched add. Closest tested cadence to 5/year is SMA 150 at 5.36 crosses/year with a $2,237 add.
- **SPY:** best OBV timing is SMA 50 (`obv_bear_rolling_10y`) at $332,445, versus monthly DCA at $337,215. It is $-4,770 relative to monthly.
  Rarest tested signal is SMA 504 at 1.73 crosses/year with a $6,948 static matched add. Closest tested cadence to 5/year is SMA 200 at 4.27 crosses/year with a $2,809 add.
- **SHOP:** best OBV timing is SMA 20 (`obv_bear_rolling_10y`) at $1,238,524, versus monthly DCA at $1,261,333. It is $-22,810 relative to monthly.
  Rarest tested signal is SMA 252 at 1.82 crosses/year with a $6,600 static matched add. Closest tested cadence to 5/year is SMA 100 at 5.55 crosses/year with a $2,164 add.

## Charts

- QQQ frequency/add sweep: [`charts/qqq_ma_sweep.png`](charts/qqq_ma_sweep.png)
- SPY frequency/add sweep: [`charts/spy_ma_sweep.png`](charts/spy_ma_sweep.png)
- SHOP frequency/add sweep: [`charts/shop_ma_sweep.png`](charts/shop_ma_sweep.png)

## Outputs

- `ma_sweep_best_by_ma.csv`
- `ma_sweep_summary.csv`
- `ma_sweep_counts_by_year.csv`
