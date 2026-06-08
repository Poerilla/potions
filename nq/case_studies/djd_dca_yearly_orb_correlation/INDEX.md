# DJD DCA, Yearly ORB, and QQQ Correlation

Data: Yahoo adjusted daily OHLCV for `DJD` and `QQQ`.
Window: **2015-12-18 through 2026-06-01** for DJD; QQQ correlation is aligned to the same dates.

Primary performance table uses the ETF yearly-ORB convention: **$10,000 starting capital**, no fees, no cash interest.
Contribution DCA sidecar uses **$1,000/month** of new cash.

Rules:

- Jan-Mar defines DJD's yearly opening range.
- Apr-Dec is the trade window.
- `stop_breakout_range_close`: resting buy stop at the OR high from Apr 1; exit next open after a daily close back below/at OR high, or year-end.
- `close_breakout_next_open`: enter next open after a fresh daily close above the OR high; same exit.
- `limit_retest_after_close`: after a fresh close above the OR high, rest a buy limit at the OR high; same exit.
- DCA rows are long-only DJD ETF exposure.

## Equity Ranking

| Rank | Variant | End Capital | Net | Return | CAGR | Max DD | Max DD % | Net/DD | Exposure |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | DJD monthly DCA cash-funded | $19,740 | $9,740 | 97.4% | 6.72% | $-1,944 | -16.59% | 5.01 | 54.9% |
| 2 | hybrid_stop_breakout_plus_monthly_dca | $20,127 | $10,127 | 101.3% | 6.92% | $-2,453 | -19.90% | 4.13 | 71.6% |
| 3 | DJD buy-and-hold | $34,068 | $24,068 | 240.7% | 12.44% | $-6,130 | -34.66% | 3.93 | 100.0% |
| 4 | 50/50 stop_breakout + monthly DCA | $15,582 | $5,582 | 55.8% | 4.33% | $-1,429 | -12.61% | 3.91 | 45.2% |
| 5 | stop_breakout_range_close | $11,423 | $1,423 | 14.2% | 1.28% | $-2,572 | -21.67% | 0.55 | 35.5% |
| 6 | close_breakout_next_open | $11,296 | $1,296 | 13.0% | 1.17% | $-2,718 | -21.91% | 0.48 | 32.6% |
| 7 | limit_retest_after_close | $10,458 | $458 | 4.6% | 0.43% | $-1,660 | -14.55% | 0.28 | 12.7% |

## Contribution DCA Sidecar

| Variant | Total Contributed | End Equity | Net | Return On Contributions | Max DD | Net/DD |
|---|---:|---:|---:|---:|---:|---:|
| DJD monthly DCA contribution | $127,000 | $250,699 | $123,699 | 97.4% | $-22,534 | 5.49 |

## Correlation With QQQ

| Sample | Observations | Correlation | DJD Avg Return | QQQ Avg Return |
|---|---:|---:|---:|---:|
| daily | 2625 | 0.651 | 0.052% | 0.085% |
| monthly | 126 | 0.604 | 1.040% | 1.719% |
| yearly | 11 | 0.413 | 11.808% | 22.192% |
| daily_when_QQQ_up | 1486 | 0.573 | 0.388% | 0.926% |
| daily_when_QQQ_down | 1136 | 0.607 | -0.384% | -1.014% |

## Trade Stats

| Variant | Trades | Win Rate | PF | Avg Return | Median Return | Avg Days | Worst | Best |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| close_breakout_next_open | 54 | 31.5% | 1.29 | 0.27% | -0.48% | 22.7 | -3.82% | 12.89% |
| stop_breakout_range_close | 76 | 30.3% | 1.29 | 0.22% | -0.40% | 17.5 | -2.54% | 13.42% |
| limit_retest_after_close | 54 | 44.4% | 1.19 | 0.10% | -0.08% | 8.8 | -2.36% | 12.39% |

## Read

- Best primary row: **DJD monthly DCA cash-funded**, ending at **$19,740** with **5.01 Net/DD**.
- DJD buy-and-hold ends at **$34,068**; cash-funded monthly DCA ends at **$19,740**.
- Daily return correlation to QQQ is **0.651**, so this is equity-correlated diversification, not an independent sleeve.

## Charts

- DJD price chart: [`charts/djd_price_full.png`](charts/djd_price_full.png)
- DJD recent price chart: [`charts/djd_price_recent.png`](charts/djd_price_recent.png)
- Equity comparison: [`charts/equity_comparison.png`](charts/equity_comparison.png)
- DJD vs QQQ correlation: [`charts/djd_qqq_correlation.png`](charts/djd_qqq_correlation.png)

## Files

- `DJD_daily.csv`
- `QQQ_common_daily.csv`
- `or_levels.csv`
- `equity_curves.csv`
- `equity_summary.csv`
- `trades.csv`
- `trade_summary.csv`
- `yearly_summary.csv`
- `contribution_dca.csv`
- `contribution_dca_summary.csv`
- `correlation_summary.csv`
- `monthly_returns.csv`
- `yearly_returns.csv`
