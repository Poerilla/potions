# Top Strategy Fair Benchmark

This report compares passive buy-and-hold to the current top broker-like strategy rows without changing any strategy rules.

Method:

- The exact normalized comparison uses the largest 3x-stress capital requirement in the selected set as the starting balance for every futures setup.
- Normalized futures rows scale each replay by `common capital / row required 3x-stress capital`; this is fractional-book comparison math, so every model is given the same stress-capital budget.
- The **$1,000,000 common-account executable table** remains as the practical whole-book view: integer futures books only, with idle cash left idle.
- QQQ rows use the same starting account and the same strategy window where a futures row is being compared.
- Strategy rows use their existing replay equity curves and are capitalized at **3 x max intrabar stress DD**.
- QQQ/SPY same-cap rows invest that exact 3x-stress capital over the same replay window as each strategy.
- The required-capital diagnostic is a fixed one-base-book comparison; it does not compound futures size. The existing `SCALING_10Y.md` report remains the account-resized compounding view.
- QQQ monthly DCA is cash-funded from the same starting capital: equal monthly buys, no new contributions, no cash interest.
- The DCA section does not compare DCA to buy-and-hold only; it compares DCA to simply sizing up the strongest same-market yearly ORB book to the same stress budget.
- This is comparison math only. It does not optimize entries, exits, sizing, or filters.

## Passive Reference

Starting capital: **$1,000,000**. Window: **2021-03-04 through 2026-03-06**.

| Benchmark | End Capital | Net | Max DD | Return | Net/DD |
|---|---:|---:|---:|---:|---:|
| SPY buy-and-hold | $1,912,123 | $912,123 | $-323,120 | 91.2% | 2.82 |
| DIA buy-and-hold | $1,675,748 | $675,748 | $-250,252 | 67.6% | 2.70 |
| 50/50 QQQ+DIA buy-and-hold | $1,854,030 | $854,030 | $-341,423 | 85.4% | 2.50 |
| QQQ buy-and-hold | $2,032,312 | $1,032,312 | $-468,200 | 103.2% | 2.20 |
| QQQ monthly DCA cash-funded | $1,557,065 | $557,065 | $-275,236 | 55.7% | 2.02 |

## Max 3x-Stress Normalized Ranking ($927,206)

This is the exact apples-to-apples capital-efficiency table. The starting balance equals the largest 3x-stress requirement among the selected futures rows, and every strategy is scaled by that balance divided by its own 3x-stress requirement. Fractional base books are allowed here because this is comparison math, not an order-size plan. The current anchor is NQ ATR daily 3-initial 10-max at $927,206.

| Rank | Strategy | Window | Scale | Base 3x Capital | Scaled Net | Return | Stress DD | Net/DD | Same-Window QQQ DCA Net | Futures - DCA |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ v2b prior-opposed ST+PMC gate S_1_1_3 | 2021-03-04 to 2026-03-06 | 5.74x | $161,541 | $6,799,226 | 733.3% | $-309,068 | 22.00 | $516,514 | $6,282,712 |
| 2 | ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 7.65x | $121,209 | $2,514,650 | 271.2% | $-309,068 | 8.14 | $3,848,371 | $-1,333,722 |
| 3 | NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 2.90x | $320,160 | $2,462,568 | 265.6% | $-309,068 | 7.97 | $3,848,371 | $-1,385,803 |
| 4 | YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | 7.76x | $119,430 | $2,241,789 | 241.8% | $-309,068 | 7.25 | $4,572,879 | $-2,331,090 |
| 5 | MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | 28.97x | $32,007 | $1,968,204 | 212.3% | $-309,068 | 6.37 | $816,433 | $1,151,771 |
| 6 | NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | 1.21x | $767,850 | $1,898,416 | 204.7% | $-309,068 | 6.14 | $3,848,371 | $-1,949,955 |
| 7 | MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | 12.07x | $76,830 | $1,772,528 | 191.2% | $-309,068 | 5.74 | $816,433 | $956,095 |
| 8 | NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | 1.00x | $927,206 | $1,717,280 | 185.2% | $-309,068 | 5.56 | $3,848,371 | $-2,131,091 |
| 9 | MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | 10.53x | $88,052 | $1,682,936 | 181.5% | $-309,068 | 5.45 | $816,433 | $866,504 |

## Common $1,000,000 Executable Ranking

This is the practical executable version: one account size for every setup, integer futures books only, and idle cash left idle. Rows are sorted by return on the common account; Net/DD is retained as the risk-efficiency check.

| Rank | Strategy | Window | Books | 3x Capital Used | Idle Cash | Futures Net | Return | Stress DD | Net/DD | Same-Window QQQ DCA Net | Futures - DCA |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ v2b prior-opposed ST+PMC gate S_1_1_3 | 2021-03-04 to 2026-03-06 | 6 | $969,246 | $30,754 | $7,107,510 | 710.8% | $-323,082 | 22.00 | $557,065 | $6,550,445 |
| 2 | ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 8 | $969,672 | $30,328 | $2,629,822 | 263.0% | $-323,224 | 8.14 | $4,150,505 | $-1,520,683 |
| 3 | NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 3 | $960,480 | $39,520 | $2,550,942 | 255.1% | $-320,160 | 7.97 | $4,150,505 | $-1,599,563 |
| 4 | YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | 8 | $955,440 | $44,560 | $2,310,054 | 231.0% | $-318,480 | 7.25 | $4,931,894 | $-2,621,840 |
| 5 | MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | 31 | $992,217 | $7,783 | $2,106,206 | 210.6% | $-330,739 | 6.37 | $880,530 | $1,225,675 |
| 6 | MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | 13 | $998,790 | $1,210 | $1,909,375 | 190.9% | $-332,930 | 5.74 | $880,530 | $1,028,845 |
| 7 | MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | 11 | $968,566 | $31,434 | $1,758,009 | 175.8% | $-322,856 | 5.45 | $880,530 | $877,479 |
| 8 | NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | 1 | $927,206 | $72,794 | $1,717,280 | 171.7% | $-309,068 | 5.56 | $4,150,505 | $-2,433,225 |
| 9 | NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | 1 | $767,850 | $232,150 | $1,572,142 | 157.2% | $-255,950 | 6.14 | $4,150,505 | $-2,578,363 |

## Required-Capital Diagnostic

This older diagnostic keeps each futures row at one base book and compares QQQ/SPY at that row’s 3x-stress required capital. Keep it for stress sizing context, but use the max-stress normalized table above for exact cross-setup ranking.

| Strategy | Window | Net | Stress DD | 3x Stress Capital | Return on 3x Capital | Net/Stress | QQQ Same-Cap Net | Strategy / QQQ Net |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| NQ v2b prior-opposed ST+PMC gate S_1_1_3 | 2021-03-04 to 2026-03-06 | $1,184,585 | $-53,847 | $161,541 | 733.3% | 22.00 | $166,761 | 7.10x |
| ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $328,728 | $-40,403 | $121,209 | 271.2% | 8.14 | $1,766,279 | 0.19x |
| NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $850,314 | $-106,720 | $320,160 | 265.6% | 7.97 | $4,665,427 | 0.18x |
| YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | $288,757 | $-39,810 | $119,430 | 241.8% | 7.25 | $2,040,828 | 0.14x |
| MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | $67,942 | $-10,669 | $32,007 | 212.3% | 6.37 | $73,401 | 0.93x |
| NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | $1,572,142 | $-255,950 | $767,850 | 204.7% | 6.14 | $11,189,244 | 0.14x |
| MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | $146,875 | $-25,610 | $76,830 | 191.2% | 5.74 | $176,194 | 0.83x |
| NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | $1,717,280 | $-309,068 | $927,206 | 185.2% | 5.56 | $13,511,400 | 0.13x |
| MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | $159,819 | $-29,350 | $88,052 | 181.5% | 5.45 | $201,928 | 0.79x |

## DCA vs Sizing Up

| DCA Strategy | Same-Stress Sized Strategy | DCA Net | DCA Stress | Sized Strategy Net | Delta vs Sized Strategy | Integer Sized Bundles Under DCA Stress |
|---|---|---:|---:|---:|---:|---:|
| NQ ATR daily ladder 1/1/2/2/2 10-max | NQ Yearly ORB scaleout3 | $1,572,142 | $-255,950 | $2,039,335 | $-467,193 | 2 |
| NQ ATR daily 3-initial 10-max | NQ Yearly ORB scaleout3 | $1,717,280 | $-309,068 | $2,462,568 | $-745,288 | 2 |
| MNQ ATR daily ladder 1/1/2/2/2 10-max | MNQ Yearly ORB scaleout3 | $146,875 | $-25,610 | $163,089 | $-16,214 | 2 |
| MNQ ATR daily 3-initial 10-max | MNQ Yearly ORB scaleout3 | $159,819 | $-29,350 | $186,909 | $-27,090 | 2 |

## QQQ DCA Exposure-Parity vs Futures

Starting capital: **$1,000,000**. For each futures row, the futures book is scaled by the QQQ monthly-DCA invested fraction over the same window. If QQQ DCA is 10% invested, futures deploys 10% of the account's 3x-stress risk capacity. This is fractional-contract comparison math, not an executable order-size plan.

| Futures Strategy | Window | QQQ DCA Avg Exposure | Futures Avg Base Units | Futures Net | Futures Stress DD | Futures Net/DD | QQQ DCA Net | QQQ DCA DD | Futures - QQQ DCA |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ v2b prior-opposed ST+PMC gate S_1_1_3 | 2021-03-04 to 2026-03-06 | 52.1% | 3.50 | $4,760,008 | $-372,750 | 12.77 | $557,065 | $-275,236 | $4,202,943 |
| MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | 55.1% | 17.26 | $1,321,691 | $-303,392 | 4.36 | $880,530 | $-352,304 | $441,160 |
| MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | 55.1% | 7.19 | $1,040,686 | $-294,283 | 3.54 | $880,530 | $-352,304 | $160,155 |
| MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | 55.1% | 6.27 | $990,843 | $-320,363 | 3.09 | $880,530 | $-352,304 | $110,313 |
| NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 60.7% | 1.90 | $2,288,318 | $-328,486 | 6.97 | $4,150,505 | $-1,102,927 | $-1,862,187 |
| ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | 60.7% | 5.02 | $2,127,815 | $-324,717 | 6.55 | $4,150,505 | $-1,102,927 | $-2,022,690 |
| NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | 60.7% | 0.79 | $1,834,362 | $-309,249 | 5.93 | $4,150,505 | $-1,102,927 | $-2,316,144 |
| NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | 60.7% | 0.66 | $1,641,019 | $-331,341 | 4.95 | $4,150,505 | $-1,102,927 | $-2,509,486 |
| YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | 60.8% | 5.10 | $1,811,579 | $-327,634 | 5.53 | $4,931,894 | $-1,091,438 | $-3,120,315 |

## Read

- The NQ prior-opposed v2b gate remains the cleanest row on capital efficiency: $1,184,585 net on $161,541 of 3x-stress capital (733.3%, 22.00 Net/Stress).
- On the max-stress normalized table, every futures row starts with $927,206; the top row is NQ v2b prior-opposed ST+PMC gate S_1_1_3 at 5.74x base size, $6,799,226 net, 733.3% return, and 22.00 Net/DD.
- On the $1,000,000 common-account table, the top executable row is NQ v2b prior-opposed ST+PMC gate S_1_1_3 with 6 books, $7,107,510 net, 710.8% return, and 22.00 Net/DD.
- Buy-and-hold is straightforward: QQQ is the strongest absolute passive benchmark in the reference window, while SPY is a little cleaner on drawdown efficiency; both remain far below the leading futures rows on Net/DD.
- QQQ monthly DCA is now tracked as its own ETF strategy row. It gives up upside versus lump-sum QQQ in this rising window, but the lower drawdown makes it a serious lower-stress passive baseline.
- The DCA check is the important wrinkle: the top NQ/MNQ ATR DCA rows do not beat simply sizing up the same-market yearly ORB book to the same stress budget.
- The exposure-parity table remains a useful QQQ-DCA deployment lens: same starting capital, and futures exposure rises with the QQQ DCA invested fraction instead of comparing a small fixed futures book to a larger gradually invested ETF account.
- Best exposure-parity futures edge over QQQ DCA: NQ v2b prior-opposed ST+PMC gate S_1_1_3 beats same-window QQQ DCA by $4,202,943 on a $1,000,000 account.
- Worst exposure-parity shortfall versus QQQ DCA: YM Yearly ORB scaleout3 trails by $3,120,315.
- At $1,000,000, full 3x-stress one-bundle feasibility is: feasible = NQ v2b prior-opposed ST+PMC gate S_1_1_3, NQ Yearly ORB scaleout3, ES Yearly ORB scaleout3, YM Yearly ORB scaleout3, MNQ Yearly ORB scaleout3, NQ ATR daily ladder 1/1/2/2/2 10-max, MNQ ATR daily ladder 1/1/2/2/2 10-max, NQ ATR daily 3-initial 10-max, MNQ ATR daily 3-initial 10-max; still above account size = none. Required-capital anchors: ES Yearly ORB scaleout3 requires $121,209; YM Yearly ORB scaleout3 requires $119,430; NQ Yearly ORB scaleout3 requires $320,160; NQ ATR daily ladder 1/1/2/2/2 10-max requires $767,850.
- Largest DCA shortfall in this comparison: NQ ATR daily 3-initial 10-max trails same-stress NQ Yearly ORB scaleout3 by $745,288.
- That does not make ATR/DCA useless; it means DCA needs to justify its operational complexity against a sized-up simpler sleeve, not just against passive QQQ.

## Outputs

- `mnq/case_studies/fair_benchmark_comparison/top_strats_3xdd_vs_buyhold.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_3xdd_daily_equity.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_passive_reference.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_qqq_monthly_dca_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_dca_same_stress.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_max_stress_normalized.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_max_stress_normalized_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_common_account_executable.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_common_account_executable_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_qqq_dca_exposure_parity.csv`
- `mnq/case_studies/fair_benchmark_comparison/top_strats_qqq_dca_exposure_parity_daily.csv`
