# Yearly-Rotating Ranks 8-10 SPY / QQQ / DIA OBV DCA Backtest

This is the annual-rotation version of the lower top-10 tranche test. Each calendar year uses an explicit beginning-of-year ranks 8, 9, and 10 schedule for SPY, QQQ, and DIA instead of applying the 2026 ranks to the past.

Mechanics: nine persistent sleeves (`SPY_8..10`, `QQQ_8..10`, `DIA_8..10`) receive one ninth of each monthly contribution. At the start of each year the target ticker for new money changes to that year's schedule. Existing shares are held; there is **no annual liquidation**, no taxes, no fees, and no cash interest.

Schedule status: `annual_ranks_8_10_schedule.csv` is a curated v0 public-holdings approximation. The mechanics are anti-hindsight; the schedule should be SEC/fund-document audited before treating the numbers as final.

Window: **2010-01-01 through 2026-06-01**. Monthly contribution pool: **$1,000**. Tested OBV SMA lengths: **20, 50, 100, 150, 200, 252, 504**.

OBV sizing rule: for each SMA, count bearish crosses across the yearly schedule, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot-year`, then each active sleeve buys `MATCHED_ADD_AVERAGE / 9` when its current ticker's own OBV bearish cross fires.

## Leaderboard

| Rank | Variant | OBV SMA | Crosses / Slot-Year | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | monthly_blind_yearly_ranks_8_10 |  |  |  |  | $542,638 | $372,638 | 219.20% | $-65,678 | 5.67 | 100.0% | $0 |
| 2 | obv_bear_sma50_yearly_ranks_8_10 | 50 | 9.68 | $1,239 | $138 | $522,877 | $352,877 | 207.57% | $-64,573 | 5.46 | 90.0% | $4,266 |
| 3 | obv_bear_sma20_yearly_ranks_8_10 | 20 | 16.15 | $743 | $83 | $520,669 | $350,669 | 206.28% | $-62,411 | 5.62 | 94.9% | $7,213 |
| 4 | obv_bear_sma200_yearly_ranks_8_10 | 200 | 4.87 | $2,466 | $274 | $493,882 | $323,882 | 190.52% | $-60,727 | 5.33 | 85.3% | $26,078 |
| 5 | obv_bear_sma150_yearly_ranks_8_10 | 150 | 5.72 | $2,098 | $233 | $477,593 | $307,593 | 180.94% | $-57,241 | 5.37 | 85.6% | $22,823 |
| 6 | obv_bear_sma100_yearly_ranks_8_10 | 100 | 6.87 | $1,746 | $194 | $476,443 | $306,443 | 180.26% | $-56,074 | 5.46 | 85.7% | $12,803 |
| 7 | obv_bear_sma252_yearly_ranks_8_10 | 252 | 3.71 | $3,234 | $359 | $470,983 | $300,983 | 177.05% | $-53,552 | 5.62 | 81.0% | $29,557 |
| 8 | obv_bear_sma504_yearly_ranks_8_10 | 504 | 2.21 | $5,418 | $602 | $450,880 | $280,880 | 165.22% | $-51,819 | 5.42 | 65.4% | $42,989 |

## Read

- Blind monthly yearly ranks 8-10 finishes at **$542,638**. Best OBV row is **SMA50** at **$522,877**, a difference of **$-19,762**.
- Closest tested cadence to 5 crosses/slot-year is **SMA200** at **4.87**, with **$2,466** matched-add average and **$274** per sleeve signal.
- This is now structurally comparable with the anti-hindsight top-three study, but both schedules are curated v0 and should be audited against provider/SEC holdings before promotion.

## QQQ / SPY Baselines

| Rank | Variant | Ending Equity | Net | Return | Max DD | Net/DD |
|---:|---|---:|---:|---:|---:|---:|
| 1 | QQQ_lump_sum | $3,133,862 | $2,963,862 | 1743.45% | $-582,247 | 5.09 |
| 2 | SPY_lump_sum | $1,520,723 | $1,350,723 | 794.54% | $-227,170 | 5.95 |
| 3 | QQQ_monthly_dca | $1,308,351 | $1,110,351 | 560.78% | $-216,105 | 5.14 |
| 4 | SPY_monthly_dca | $772,121 | $574,121 | 289.96% | $-110,777 | 5.18 |
| 5 | monthly_blind_yearly_ranks_8_10 | $542,638 | $372,638 | 219.20% | $-65,678 | 5.67 |
| 6 | obv_bear_sma50_yearly_ranks_8_10 | $522,877 | $352,877 | 207.57% | $-64,573 | 5.46 |

## Annual Schedule

| Year | SPY Ranks 8-10 | QQQ Ranks 8-10 | DIA Ranks 8-10 |
|---:|---|---|---|
| 2010 | JPM / CVX / WMT | INTC / AMZN / GILD | MCD / CAT / BA |
| 2011 | JPM / CVX / WMT | INTC / ORCL / AMZN | MCD / CAT / BA |
| 2012 | IBM / CVX / GE | ORCL / AMZN / GILD | MCD / CAT / BA |
| 2013 | BRK-B / WMT / WFC | ORCL / AMZN / GILD | MCD / CAT / BA |
| 2014 | BRK-B / JNJ / WFC | GILD / INTC / AMZN | AXP / MCD / CAT |
| 2015 | BRK-B / JNJ / GE | GILD / INTC / AMGN | AXP / MCD / BA |
| 2016 | BRK-B / JNJ / GE | GILD / INTC / AMGN | AXP / MCD / BA |
| 2017 | META / JNJ / JPM | CMCSA / INTC / CSCO | UNH / HD / MCD |
| 2018 | META / JNJ / JPM | INTC / CMCSA / PEP | UNH / HD / MCD |
| 2019 | META / BRK-B / JPM | CMCSA / PEP / CSCO | HD / MCD / NKE |
| 2020 | GOOGL / GOOG / BRK-B | PEP / CMCSA / COST | UNH / HD / MCD |
| 2021 | TSLA / GOOGL / GOOG | NFLX / PEP / CMCSA | MSFT / AMGN / CAT |
| 2022 | TSLA / GOOGL / GOOG | NFLX / PEP / COST | MSFT / AMGN / CAT |
| 2023 | NVDA / GOOGL / GOOG | PEP / COST / ADBE | MSFT / CAT / MCD |
| 2024 | META / BRK-B / GOOGL | TSLA / AVGO / COST | MSFT / CAT / AXP |
| 2025 | META / TSLA / AVGO | TSLA / AVGO / GOOG | AXP / AAPL / SHW |
| 2026 | META / TSLA / MU | TSLA / AVGO / GOOG | AXP / AAPL / SHW |

## Charts

- Equity leaderboard: [`charts/equity_yearly_ranks_8_10.png`](charts/equity_yearly_ranks_8_10.png)
- Frequency/add sizing: [`charts/frequency_add_yearly_ranks_8_10.png`](charts/frequency_add_yearly_ranks_8_10.png)

## Outputs

- `leaderboard.csv`
- `etf_baseline_comparison.csv`
- `daily_equity.csv`
- `transactions.csv`
- `annual_ranks_8_10_schedule.csv`
