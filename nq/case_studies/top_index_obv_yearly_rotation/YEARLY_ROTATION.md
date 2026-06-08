# Yearly-Rotating Top SPY / QQQ / DIA OBV DCA Backtest

This is the anti-hindsight version of the top-index-stock OBV DCA study. Each calendar year uses an explicit beginning-of-year top-three schedule for SPY, QQQ, and DIA instead of applying 2026 winners to the past.

Mechanics: nine persistent sleeves (`SPY_1..3`, `QQQ_1..3`, `DIA_1..3`) receive one ninth of each monthly contribution. At the start of each year the target ticker for new money changes to that year's schedule. Existing shares are held; there is **no annual liquidation**, no taxes, no fees, and no cash interest.

Schedule status: `annual_top3_schedule.csv` is a curated v0 public-top-holdings schedule. The backtest mechanics are anti-hindsight; the schedule itself should be SEC/fund-document audited before treating the numbers as final.

Window: **2010-01-01 through 2026-06-01**. Monthly contribution pool: **$1,000**. Tested OBV SMA lengths: **20, 50, 100, 150, 200, 252, 504**.

OBV sizing rule: for each SMA, count bearish crosses across the yearly schedule, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot-year`, then each active sleeve buys `MATCHED_ADD_AVERAGE / 9` when its current ticker's own OBV bearish cross fires.

## Leaderboard

| Rank | Variant | OBV SMA | Crosses / Slot-Year | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | monthly_blind_yearly_top3 |  |  |  |  | $1,309,697 | $1,111,697 | 561.46% | $-247,844 | 4.49 | 100.0% | $0 |
| 2 | obv_bear_sma20_yearly_top3 | 20 | 17.46 | $687 | $76 | $1,228,973 | $1,030,973 | 520.69% | $-227,256 | 4.54 | 94.3% | $6,664 |
| 3 | obv_bear_sma50_yearly_top3 | 50 | 10.69 | $1,122 | $125 | $1,183,122 | $985,122 | 497.54% | $-215,417 | 4.57 | 90.7% | $8,503 |
| 4 | obv_bear_sma100_yearly_top3 | 100 | 7.51 | $1,598 | $178 | $1,175,254 | $977,254 | 493.56% | $-216,314 | 4.52 | 84.2% | $9,574 |
| 5 | obv_bear_sma150_yearly_top3 | 150 | 6.03 | $1,989 | $221 | $1,153,477 | $955,477 | 482.56% | $-212,087 | 4.51 | 83.1% | $16,629 |
| 6 | obv_bear_sma252_yearly_top3 | 252 | 4.14 | $2,900 | $322 | $1,131,037 | $933,037 | 471.23% | $-201,522 | 4.63 | 79.9% | $32,859 |
| 7 | obv_bear_sma200_yearly_top3 | 200 | 5.13 | $2,339 | $260 | $1,113,287 | $915,287 | 462.27% | $-206,297 | 4.44 | 82.3% | $18,147 |
| 8 | obv_bear_sma504_yearly_top3 | 504 | 2.20 | $5,464 | $607 | $828,052 | $630,052 | 318.21% | $-154,333 | 4.08 | 61.0% | $32,337 |

## Read

- Best OBV yearly-rotation row is **SMA20** at **$1,228,973**, versus blind monthly yearly-rotation DCA at **$1,309,697**. Difference: **$-80,724**.
- Closest tested cadence to 5 crosses/slot-year is **SMA200** at **5.13**, with **$2,339** matched-add average and **$260** per sleeve signal.
- Compared with the static 2026-holdings leaderboard, the annual schedule removes most of the early-NVDA hindsight edge. This is the right structure for future top-holdings research.

## Annual Schedule

| Year | SPY Top 3 | QQQ Top 3 | DIA Top 3 |
|---:|---|---|---|
| 2010 | XOM / MSFT / AAPL | AAPL / MSFT / QCOM | IBM / CVX / MMM |
| 2011 | XOM / AAPL / MSFT | AAPL / MSFT / GOOGL | IBM / CVX / MMM |
| 2012 | AAPL / XOM / MSFT | AAPL / MSFT / GOOGL | IBM / CVX / MMM |
| 2013 | AAPL / XOM / GOOGL | AAPL / MSFT / GOOGL | IBM / CVX / MMM |
| 2014 | AAPL / XOM / GOOGL | AAPL / MSFT / GOOGL | IBM / V / GS |
| 2015 | AAPL / MSFT / XOM | AAPL / MSFT / GOOGL | V / GS / IBM |
| 2016 | AAPL / MSFT / XOM | AAPL / MSFT / AMZN | GS / IBM / MMM |
| 2017 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | GS / BA / MMM |
| 2018 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | BA / GS / MMM |
| 2019 | MSFT / AAPL / AMZN | MSFT / AAPL / AMZN | BA / UNH / GS |
| 2020 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | BA / UNH / GS |
| 2021 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | UNH / GS / HD |
| 2022 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | UNH / GS / HD |
| 2023 | AAPL / MSFT / AMZN | AAPL / MSFT / AMZN | UNH / GS / MSFT |
| 2024 | MSFT / AAPL / NVDA | MSFT / AAPL / NVDA | UNH / GS / MSFT |
| 2025 | NVDA / AAPL / MSFT | NVDA / AAPL / MSFT | GS / UNH / MSFT |
| 2026 | NVDA / AAPL / MSFT | NVDA / AAPL / MSFT | GS / CAT / MSFT |

## QQQ / SPY Baselines

| Rank | Variant | Ending Equity | Net | Return | Max DD | Net/DD |
|---:|---|---:|---:|---:|---:|---:|
| 1 | QQQ_lump_sum | $3,650,027 | $3,452,027 | 1743.45% | $-678,146 | 5.09 |
| 2 | SPY_lump_sum | $1,771,195 | $1,573,195 | 794.54% | $-264,586 | 5.95 |
| 3 | monthly_blind_yearly_top3 | $1,309,697 | $1,111,697 | 561.46% | $-247,844 | 4.49 |
| 4 | QQQ_monthly_dca | $1,308,351 | $1,110,351 | 560.78% | $-216,105 | 5.14 |
| 5 | obv_bear_sma20_yearly_top3 | $1,228,973 | $1,030,973 | 520.69% | $-227,256 | 4.54 |
| 6 | obv_bear_sma50_yearly_top3 | $1,183,122 | $985,122 | 497.54% | $-215,417 | 4.57 |
| 7 | SPY_monthly_dca | $772,121 | $574,121 | 289.96% | $-110,777 | 5.18 |

Read: the apples-to-apples monthly-cashflow comparison is almost even with QQQ DCA: yearly-rotating top-three monthly DCA finishes about $1,346 ahead of QQQ monthly DCA, but QQQ has a smaller max drawdown and higher Net/DD. Lump-sum QQQ/SPY are shown separately because they use all $198,000 on day one, which is a different cashflow than `$1,000/month` DCA.

## Charts

- Equity leaderboard: [`charts/equity_yearly_rotation.png`](charts/equity_yearly_rotation.png)
- Frequency/add sizing: [`charts/frequency_add_yearly_rotation.png`](charts/frequency_add_yearly_rotation.png)

## Outputs

- `leaderboard.csv`
- `etf_baseline_comparison.csv`
- `daily_equity.csv`
- `transactions.csv`
- `annual_top3_schedule.csv`
