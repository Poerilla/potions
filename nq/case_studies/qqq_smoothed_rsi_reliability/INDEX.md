# QQQ Smoothed-RSI Reliability Study

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-03 through 2026-06-02**.

Indicator:

- RSI uses Wilder-style RSI(14).
- Smoothed RSI is EMA(14) of RSI(14).
- Overbought starts when smoothed RSI first touches **>= 70** after being below it.
- Oversold buy starts when smoothed RSI first touches **<= 30** after being above it.

## Overbought Interval Summary

For each overbought start, the interval is measured from that date until the next overbought start. The table uses adjusted highs/lows inside that interval.

| Sample | Events | Median Low | Median High | Median High-Low Range | Pullback >=5% | >=10% | >=15% | >=20% | Low Before High | Median Bars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_overbought_intervals | 29 | -4.00% | 10.93% | 22.44% | 48.3% | 37.9% | 17.2% | 10.3% | 93.1% | 137 |
| completed_intervals_only | 28 | -5.30% | 11.78% | 22.71% | 50.0% | 39.3% | 17.9% | 10.7% | 92.9% | 144 |

## Forward Return Check

| Horizon | Observations | Avg Return | Median Return | Positive | <= -5% | <= -10% |
|---|---:|---:|---:|---:|---:|---:|
| 21d | 28 | -0.88% | -0.08% | 50.0% | 10.7% | 7.1% |
| 63d | 28 | 1.03% | 1.34% | 57.1% | 7.1% | 0.0% |
| 126d | 28 | 7.76% | 9.53% | 89.3% | 3.6% | 0.0% |
| 252d | 27 | 15.62% | 13.79% | 92.6% | 3.7% | 3.7% |

## Oversold-Touch Lump Buy Test

Comparison rule: contribute **$1,000/month**. Monthly DCA buys each first trading day. Oversold-touch variants hold contributions as cash and buy only on smoothed-RSI oversold starts. `static_full_window` sizes each signal as `$12k / observed oversold touches per year`; rolling rows estimate touch frequency from prior history and cap buys at available cash.

| Rank | Variant | Touches / Yr | Matched Add | Buys | Avg Buy | End Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | monthly_blind_dca | 0.11 | rolling/NA | 318 | $1,000 | $4,010,043 | $3,692,043 | 1161.0% | $-714,102 | 5.17 | 100.0% | $0 |
| 2 | oversold_static_full_window | 0.11 | $105,648 | 2 | $53,000 | $3,205,407 | $2,887,407 | 908.0% | $-542,621 | 5.32 | 70.3% | $212,000 |
| 3 | oversold_rolling_3y | 0.11 | rolling/NA | 3 | $12,000 | $1,327,587 | $1,009,587 | 317.5% | $-183,029 | 5.52 | 43.1% | $282,000 |
| 4 | oversold_rolling_5y | 0.11 | rolling/NA | 3 | $12,000 | $1,327,587 | $1,009,587 | 317.5% | $-183,029 | 5.52 | 43.1% | $282,000 |
| 5 | oversold_rolling_10y | 0.11 | rolling/NA | 3 | $12,000 | $1,327,587 | $1,009,587 | 317.5% | $-183,029 | 5.52 | 43.1% | $282,000 |

## Oversold Threshold Sweep

This sweep reruns the static matched-add rule across smoothed-RSI buy thresholds from 30.0 to 70.0. `Deployed` is the share of contributed cash that actually got invested by the final bar; this is the key apples-to-apples check against monthly DCA.

| Check | Threshold | Touches | Touches / Yr | Matched Add | Deployed | End Equity | Vs Monthly DCA |
|---|---:|---:|---:|---:|---:|---:|---:|
| First >=90% deployed | 45.0 | 74 | 2.80 | $4,283 | 91.5% | $3,738,568 | $-271,475 |
| First >=95% deployed | 51.5 | 99 | 3.75 | $3,201 | 95.4% | $3,884,037 | $-126,006 |
| Best ending equity | 49.5 | 89 | 3.37 | $3,561 | 93.6% | $3,903,024 | $-107,020 |
| Most touch starts | 53.0 | 111 | 4.20 | $2,855 | 96.2% | $3,786,925 | $-223,118 |

- The first threshold that deployed at least **90%** of contributions was **45.0**; the first that deployed at least **95%** was **51.5**.
- The best ending-equity threshold was **49.5** at **$3,903,024**, still **$-107,020** versus monthly DCA.
- No swept threshold beat monthly DCA on ending equity.

## Second-Threshold Lump Buy Test

This variant contributes the same **$1,000/month**, but cash stays idle until the smoothed RSI first arms below a higher threshold, then it buys **all available cash once** if the same drawdown episode reaches the buy threshold. It resets only after smoothed RSI recovers above the arm threshold.

| Check | Arm | Buy | Buys | Deployed | End Equity | Vs Monthly DCA | Net/DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Best overall lump row | 60.0 | 60.0 | 79 | 97.8% | $4,093,596 | $83,553 | 5.17 |
| Best true second-threshold row | 60.0 | 57.5 | 68 | 97.8% | $4,079,003 | $68,960 | 5.17 |

- The best true second-threshold row **did** beat monthly DCA on ending equity.
- This is a stronger result than the matched-add touch sweep, but it depends on sweeping all accumulated cash at the trigger, so it is more of a cash-timing strategy than a smooth DCA replacement.

## Holdout / Walk-Forward Check

Holdout and walk-forward use only prior data to choose thresholds. The fixed holdout trains before the holdout year and then freezes the chosen thresholds. The yearly walk-forward reselects thresholds each January using all data before that year, then stitches the out-of-sample account path forward with cash and shares carried through time.

### Fixed Holdout

| Variant | Train/Test | Selected Arm | Selected Buy | Buys | End Equity | Vs Monthly | Max DD | Net/DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| holdout_monthly_dca | 2000-01-03 to 2015-12-31 / 2016-01-04 to 2026-06-02 |  |  | 126 | $426,730 | $0 | $-64,689 | 4.65 |
| holdout_best_overall_lump | 2000-01-03 to 2015-12-31 / 2016-01-04 to 2026-06-02 | 60.0 | 60.0 | 34 | $409,343 | $-17,387 | $-61,474 | 4.61 |
| holdout_best_true_second_lump | 2000-01-03 to 2015-12-31 / 2016-01-04 to 2026-06-02 | 60.0 | 57.5 | 29 | $409,864 | $-16,866 | $-61,562 | 4.61 |

### Yearly Walk-Forward

| Variant | Selected Years | Buys | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| walkforward_monthly_dca | 17 | 198 | $1,314,375 | $0 | $-216,104 | 5.17 | 100.0% |
| walkforward_best_overall_lump | 17 | 44 | $977,133 | $-337,242 | $-154,506 | 5.04 | 68.8% |
| walkforward_best_true_second_lump | 17 | 38 | $976,990 | $-337,385 | $-154,484 | 5.04 | 68.7% |

- Most common yearly-selected true second-threshold rule: **arm 60.0 / buy 57.5** in **12** years.
- Most common yearly-selected overall rule: **arm 60.0 / buy 60.0** in **12** years.

- Validation read: the full-sample second-threshold edge **did not survive** the out-of-sample checks. The best fixed-holdout timing row trailed monthly DCA by **$16,866**, and the best yearly walk-forward timing row trailed by **$337,242**.

## Read

- Completed overbought intervals measured: **28**.
- Median interval low after an overbought start was **-5.30%** from the event close; median interval high was **11.78%**.
- Overbought was **not** a reliable bearish sell signal in this QQQ sample: the median completed interval low was -5.30%, but the median interval high was 11.78% and the median 126d/252d forward returns stayed positive.
- Oversold starts were rare: **3** total (**2001-09-21, 2008-10-09, 2008-10-15**).
- Oversold starts occurred at about **0.11/year**. The best oversold-touch lump-buy row was **oversold_static_full_window** at **$3,205,407**, versus monthly DCA at **$4,010,043**.
- On ending equity, oversold-touch lump buying **did not beat** traditional monthly DCA in this test.

## Charts

- Overbought interval high/low: [`charts/overbought_interval_high_low.png`](charts/overbought_interval_high_low.png)
- DCA comparison: [`charts/oversold_touch_dca_vs_monthly.png`](charts/oversold_touch_dca_vs_monthly.png)
- Oversold threshold sweep: [`charts/oversold_threshold_sweep.png`](charts/oversold_threshold_sweep.png)
- Second-threshold lump sweep: [`charts/two_stage_lump_sweep.png`](charts/two_stage_lump_sweep.png)
- Fixed holdout equity: [`charts/holdout_equity.png`](charts/holdout_equity.png)
- Yearly walk-forward equity: [`charts/walkforward_equity.png`](charts/walkforward_equity.png)

## Files

- `QQQ_smoothed_rsi_daily.csv`
- `overbought_intervals.csv`
- `overbought_summary.csv`
- `overbought_forward_returns.csv`
- `overbought_forward_summary.csv`
- `oversold_touch_dca_summary.csv`
- `oversold_touch_dca_daily.csv`
- `oversold_threshold_sweep.csv`
- `two_stage_lump_sweep.csv`
- `holdout_summary.csv`
- `holdout_daily.csv`
- `walkforward_selection_by_year.csv`
- `walkforward_summary.csv`
- `walkforward_daily.csv`
