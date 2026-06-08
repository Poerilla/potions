# QQQ / SPY / SHOP OBV Bearish-Cross DCA Study

Rule: calculate daily OBV from adjusted close direction and raw Yahoo volume, then buy only when OBV crosses below its 20-day SMA.

Comparison model:

- Blind monthly DCA buys `$1,000` on the first trading day of each month.
- OBV bearish-cross DCA receives the same monthly contribution, holds it as cash, and buys only on bearish OBV crosses.
- `static_full_window` uses the observed bearish-cross frequency over the study window to size each signal buy: annual monthly budget divided by bearish crosses per year.
- Rolling variants estimate bearish-cross frequency from prior 1y/2y/3y/5y/10y lookbacks and cap purchases at available cash.
- No sells, no fees, no cash interest, no optimization of OBV length.

Window: **2015-06-01 through 2026-06-01**. Monthly contribution: **$1,000**.

## Frequency And Suggested Adds

| Ticker | Bear Crosses | Crosses / Year | Static Add To Match $12k/Yr | Best Deployment Variant | Ending Cash | Ending Cash % |
|---|---:|---:|---:|---|---:|---:|
| QQQ | 189 | 17.18 | $698 | obv_bear_rolling_10y | $3,290 | 2.47% |
| SPY | 202 | 18.36 | $654 | obv_bear_rolling_2y | $2,333 | 1.75% |
| SHOP | 169 | 15.36 | $781 | obv_bear_rolling_10y | $1,236 | 0.93% |

## Performance Summary

| Ticker | Variant | Buys | Avg Buy | Total Contributed | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QQQ | monthly_blind_dca | 133 | $1,000 | $133,000 | $476,490 | $343,490 | 258.26% | $-73,188 | 4.69 | 100.0% | $0 |
| QQQ | obv_bear_static_full_window | 185 | $689 | $133,000 | $446,592 | $313,592 | 235.78% | $-67,231 | 4.66 | 92.9% | $5,502 |
| QQQ | obv_bear_rolling_1y | 173 | $748 | $133,000 | $461,370 | $328,370 | 246.89% | $-70,324 | 4.67 | 95.3% | $3,627 |
| QQQ | obv_bear_rolling_2y | 172 | $754 | $133,000 | $456,616 | $323,616 | 243.32% | $-69,211 | 4.68 | 95.5% | $3,326 |
| QQQ | obv_bear_rolling_3y | 168 | $762 | $133,000 | $452,983 | $319,983 | 240.59% | $-68,438 | 4.68 | 95.3% | $4,922 |
| QQQ | obv_bear_rolling_5y | 158 | $821 | $133,000 | $460,227 | $327,227 | 246.04% | $-70,092 | 4.67 | 96.2% | $3,348 |
| QQQ | obv_bear_rolling_10y (best match) | 133 | $975 | $133,000 | $469,309 | $336,309 | 252.86% | $-71,993 | 4.67 | 97.4% | $3,290 |
| SPY | monthly_blind_dca | 133 | $1,000 | $133,000 | $337,215 | $204,215 | 153.55% | $-45,809 | 4.46 | 100.0% | $0 |
| SPY | obv_bear_static_full_window | 197 | $647 | $133,000 | $323,507 | $190,507 | 143.24% | $-42,701 | 4.46 | 92.4% | $5,483 |
| SPY | obv_bear_rolling_1y | 188 | $694 | $133,000 | $327,510 | $194,510 | 146.25% | $-44,109 | 4.41 | 95.3% | $2,455 |
| SPY | obv_bear_rolling_2y (best match) | 181 | $722 | $133,000 | $321,913 | $188,913 | 142.04% | $-42,662 | 4.43 | 94.3% | $2,333 |
| SPY | obv_bear_rolling_3y | 178 | $729 | $133,000 | $324,425 | $191,425 | 143.93% | $-42,738 | 4.48 | 95.7% | $3,186 |
| SPY | obv_bear_rolling_5y | 170 | $753 | $133,000 | $327,265 | $194,265 | 146.06% | $-43,367 | 4.48 | 96.5% | $5,010 |
| SPY | obv_bear_rolling_10y | 142 | $920 | $133,000 | $331,919 | $198,919 | 149.56% | $-44,484 | 4.47 | 97.5% | $2,351 |
| SHOP | monthly_blind_dca | 133 | $1,000 | $133,000 | $1,261,333 | $1,128,333 | 848.37% | $-1,333,020 | 0.85 | 100.0% | $0 |
| SHOP | obv_bear_static_full_window | 169 | $780 | $133,000 | $1,069,247 | $936,247 | 703.94% | $-1,095,677 | 0.85 | 93.8% | $1,241 |
| SHOP | obv_bear_rolling_1y | 159 | $824 | $133,000 | $1,180,594 | $1,047,594 | 787.66% | $-1,232,864 | 0.85 | 96.9% | $1,911 |
| SHOP | obv_bear_rolling_2y | 154 | $855 | $133,000 | $1,207,033 | $1,074,033 | 807.54% | $-1,266,697 | 0.85 | 97.3% | $1,386 |
| SHOP | obv_bear_rolling_3y | 154 | $855 | $133,000 | $1,211,417 | $1,078,417 | 810.84% | $-1,273,355 | 0.85 | 97.5% | $1,265 |
| SHOP | obv_bear_rolling_5y | 148 | $890 | $133,000 | $1,230,613 | $1,097,613 | 825.27% | $-1,295,215 | 0.85 | 97.7% | $1,286 |
| SHOP | obv_bear_rolling_10y (best match) | 122 | $1,080 | $133,000 | $1,238,524 | $1,105,524 | 831.22% | $-1,306,562 | 0.85 | 97.9% | $1,236 |

## Read

- **QQQ:** bearish crosses average 17.18/year, implying a static matched add of $698 per signal versus $1,000 monthly. Best deployment match is `obv_bear_rolling_10y`; best ending equity is `monthly_blind_dca` at $476,490.
  Monthly DCA ending equity/net: $476,490 / $343,490; static OBV ending equity/net: $446,592 / $313,592.
- **SPY:** bearish crosses average 18.36/year, implying a static matched add of $654 per signal versus $1,000 monthly. Best deployment match is `obv_bear_rolling_2y`; best ending equity is `monthly_blind_dca` at $337,215.
  Monthly DCA ending equity/net: $337,215 / $204,215; static OBV ending equity/net: $323,507 / $190,507.
- **SHOP:** bearish crosses average 15.36/year, implying a static matched add of $781 per signal versus $1,000 monthly. Best deployment match is `obv_bear_rolling_10y`; best ending equity is `monthly_blind_dca` at $1,261,333.
  Monthly DCA ending equity/net: $1,261,333 / $1,128,333; static OBV ending equity/net: $1,069,247 / $936,247.

## Charts

- QQQ equity curves: [`charts/qqq_equity.png`](charts/qqq_equity.png); OBV signals: [`charts/qqq_obv.png`](charts/qqq_obv.png)
- SPY equity curves: [`charts/spy_equity.png`](charts/spy_equity.png); OBV signals: [`charts/spy_obv.png`](charts/spy_obv.png)
- SHOP equity curves: [`charts/shop_equity.png`](charts/shop_equity.png); OBV signals: [`charts/shop_obv.png`](charts/shop_obv.png)

## Outputs

- `summary.csv`
- `daily_equity.csv`
- `bear_cross_counts_by_year.csv`
- `signals.csv`
