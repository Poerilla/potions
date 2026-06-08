# Current Bottom-3-of-Top-10 SPY / QQQ / DIA OBV DCA Diagnostic

Nine-slot portfolio built from current ranks **8, 9, and 10** of each ETF/index top-10 holding list. Duplicate names are preserved as separate slots. This is a **static current-holdings diagnostic**, not an anti-hindsight historical holdings backtest.

Sources: [SPY](https://stockanalysis.com/etf/spy/holdings/) ranks 8-10 META / TSLA / MU, as of Jun 1, 2026; [QQQ](https://stockanalysis.com/etf/qqq/holdings/) ranks 8-10 TSLA / AVGO / GOOG, as of May 29, 2026; [DIA](https://stockanalysis.com/etf/dia/holdings/) ranks 8-10 AXP / AAPL / SHW, as of May 28, 2026.

Window: **2015-06-01 through 2026-06-01**. Monthly contribution pool: **$1,000**. Tested OBV SMA lengths: **20, 50, 100, 150, 200, 252, 504**.

Add sizing rule: for each OBV SMA, calculate the average bearish-cross frequency across the nine slots, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot per year`, then buy `MATCHED_ADD_AVERAGE / 9` in each slot when that slot's own OBV bearish cross fires.

## Selected Slots

| Slot | Index Source | Rank | Ticker | Name |
|---|---|---:|---|---|
| SPY_8_META | S&P 500 / SPY | 8 | META | Meta Platforms |
| SPY_9_TSLA | S&P 500 / SPY | 9 | TSLA | Tesla |
| SPY_10_MU | S&P 500 / SPY | 10 | MU | Micron Technology |
| QQQ_8_TSLA | Nasdaq-100 / QQQ | 8 | TSLA | Tesla |
| QQQ_9_AVGO | Nasdaq-100 / QQQ | 9 | AVGO | Broadcom |
| QQQ_10_GOOG | Nasdaq-100 / QQQ | 10 | GOOG | Alphabet Class C |
| DIA_8_AXP | Dow / DIA | 8 | AXP | American Express |
| DIA_9_AAPL | Dow / DIA | 9 | AAPL | Apple |
| DIA_10_SHW | Dow / DIA | 10 | SHW | Sherwin-Williams |

## Leaderboard

| Rank | Variant | OBV SMA | Avg Crosses / Slot / Yr | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | monthly_blind_bottom_top10 |  |  |  |  | $1,226,258 | $1,093,258 | 822.00% | $-308,990 | 3.54 | 100.0% | $0 |
| 2 | obv_bear_sma20_bottom_top10 | 20 | 17.00 | $706 | $78 | $1,154,462 | $1,021,462 | 768.02% | $-283,138 | 3.61 | 92.1% | $8,833 |
| 3 | obv_bear_sma50_bottom_top10 | 50 | 10.93 | $1,098 | $122 | $1,126,880 | $993,880 | 747.28% | $-269,916 | 3.68 | 87.3% | $9,867 |
| 4 | obv_bear_sma100_bottom_top10 | 100 | 7.02 | $1,709 | $190 | $1,012,644 | $879,644 | 661.39% | $-247,728 | 3.55 | 81.7% | $9,605 |
| 5 | obv_bear_sma252_bottom_top10 | 252 | 3.44 | $3,484 | $387 | $974,743 | $841,743 | 632.89% | $-226,469 | 3.72 | 74.5% | $22,026 |
| 6 | obv_bear_sma200_bottom_top10 | 200 | 4.26 | $2,815 | $313 | $917,756 | $784,756 | 590.04% | $-218,812 | 3.59 | 75.9% | $16,994 |
| 7 | obv_bear_sma150_bottom_top10 | 150 | 5.37 | $2,233 | $248 | $856,682 | $723,682 | 544.12% | $-205,747 | 3.52 | 77.8% | $15,177 |
| 8 | obv_bear_sma504_bottom_top10 | 504 | 2.08 | $5,767 | $641 | $775,308 | $642,308 | 482.94% | $-147,868 | 4.34 | 57.2% | $38,037 |

## Read

- Blind monthly bottom-top10 DCA finishes at **$1,226,258**. Best OBV timing is **SMA20** at **$1,154,462**, a difference of **$-71,796**.
- Closest tested cadence to 5 crosses/slot/year is **SMA150** at **5.37**, with **$2,233** matched-add average and **$248** per-slot signal.
- This lower top-10 tranche is more speculative/concentrated than QQQ/SPY itself and should be treated as diagnostic until a yearly ranks-8-to-10 historical schedule is built.

## Best OBV Slot Breakdown

| Slot | Ticker | Crosses / Yr | Buys | Avg Buy | Ending Equity | Net | Ending Cash |
|---|---|---:|---:|---:|---:|---:|---:|
| DIA_8_AXP | AXP | 16.36 | 179 | $78 | $39,780 | $25,002 | $856 |
| DIA_9_AAPL | AAPL | 17.27 | 187 | $77 | $68,751 | $53,974 | $418 |
| DIA_10_SHW | SHW | 17.27 | 184 | $77 | $25,622 | $10,844 | $587 |
| QQQ_8_TSLA | TSLA | 17.64 | 179 | $75 | $154,637 | $139,859 | $1,313 |
| QQQ_9_AVGO | AVGO | 17.64 | 185 | $77 | $222,647 | $207,869 | $608 |
| QQQ_10_GOOG | GOOG | 15.45 | 166 | $76 | $69,837 | $55,059 | $2,097 |
| SPY_8_META | META | 16.73 | 184 | $77 | $40,082 | $25,304 | $562 |
| SPY_9_TSLA | TSLA | 17.64 | 179 | $75 | $154,637 | $139,859 | $1,313 |
| SPY_10_MU | MU | 17.00 | 181 | $76 | $378,469 | $363,691 | $1,078 |

## Charts

- Equity leaderboard: [`charts/equity_leaderboard.png`](charts/equity_leaderboard.png)
- Frequency/add sizing: [`charts/frequency_add_by_ma.png`](charts/frequency_add_by_ma.png)

## Outputs

- `leaderboard.csv`
- `daily_equity.csv`
- `slot_summary.csv`
- `selected_slots.csv`
