# Fair Benchmark Comparison

Window: **2020-01-01 through 2025-12-31**. Starting capital: **$50,000**.

Purpose: TradingView buy-and-hold assumes the full initial capital is passively exposed to the chart symbol for the full test. That is not apples-to-apples against a futures system that uses only a risk-sized sleeve and can sit in cash. This report compares both sides from the same starting capital.

Futures rows include both a fixed one-bundle sleeve and an annual risk-scaled sleeve. The annual scaling rule chooses `floor(current capital / (3 x base open-heat stress DD))` bundles at each calendar-year start. ETF benchmarks invest the full starting capital and hold through the window. ETF data uses Yahoo chart adjusted close, cached under `data/benchmarks/`.

## Summary

| Sleeve | End Capital | Net | Max DD / Stress DD | Return | Net/DD | Peak Size |
|---|---:|---:|---:|---:|---:|---:|
| Yearly ORB MNQ standalone (1 bundle fixed) | $118,082 | $68,082 | $-4,604 | 136.2% | 14.79 | 1 bundles / 3 contracts |
| Yearly ORB MNQ standalone (3x DD annual scale) | $1,454,862 | $1,404,862 | $-171,840 | 2809.7% | 8.18 | 48 bundles / 144 contracts |
| Yearly ORB MNQ+MYM portfolio (1 bundle fixed) | $185,878 | $135,878 | $-6,240 | 271.8% | 21.78 | 1 bundles / 15 contracts |
| Yearly ORB MNQ+MYM portfolio (3x DD annual scale) | $3,942,948 | $3,892,948 | $-287,100 | 7785.9% | 13.56 | 75 bundles / 1125 contracts |
| QQQ buy-and-hold | $147,260 | $97,260 | $-33,121 | 194.5% | 2.94 | full ETF capital |
| DIA buy-and-hold | $92,926 | $42,926 | $-18,808 | 85.9% | 2.28 | full ETF capital |
| SPY buy-and-hold | $114,532 | $64,532 | $-19,083 | 129.1% | 3.38 | full ETF capital |
| 50/50 QQQ+DIA buy-and-hold | $120,093 | $70,093 | $-22,327 | 140.2% | 3.14 | full ETF capital |

## Read

- The ETF rows are a useful passive-capital benchmark, but they accept full drawdown exposure with no stop or de-risking.
- The fixed futures rows show what a single strategy sleeve would have done inside a `$50k` account without compounding size.
- The annual risk-scaled futures rows show what the same `$50k` would have done under the existing 3x stress-DD rule. This is closer to how we would actually capitalize and grow a futures test account, but the ending contract counts can become operationally unrealistic.
- This is still not a forecast. It is a fairer normalization layer for comparing passive exposure against a rules-based futures sleeve.

## Outputs

- `mnq/case_studies/fair_benchmark_comparison/yearly_orb_mnq_standalone_fixed_1bundle_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/yearly_orb_mnq_standalone_3xdd_annual_scale_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/yearly_orb_mnq_mym_portfolio_fixed_1bundle_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/yearly_orb_mnq_mym_portfolio_3xdd_annual_scale_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/qqq_buy_and_hold_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/dia_buy_and_hold_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/spy_buy_and_hold_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/5050_qqq_dia_buy_and_hold_50k_daily.csv`
- `mnq/case_studies/fair_benchmark_comparison/summary.csv`
