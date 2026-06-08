# Top SPY / QQQ / DIA Holdings OBV DCA Leaderboard

Nine-slot portfolio built from the current top three holdings of SPY/S&P 500, QQQ/Nasdaq-100, and DIA/Dow. Duplicate names are preserved as separate slots, so MSFT has three sleeves and NVDA/AAPL have two sleeves. Each slot receives one ninth of the monthly contribution and buys only when its own ticker's OBV crosses bearish.

Holdings source links: [SPY](https://stockanalysis.com/etf/spy/holdings/), [QQQ](https://stockanalysis.com/etf/qqq/), [DIA](https://stockanalysis.com/etf/dia/holdings/).

Window: **2015-06-01 through 2026-06-01**. Monthly contribution pool: **$1,000**. Tested OBV SMA lengths: **20, 50, 100, 150, 200, 252, 504**.

Add sizing rule: for each OBV SMA, calculate the average bearish-cross frequency across the nine slots, set `MATCHED_ADD_AVERAGE = $12k / average crosses per slot per year`, then buy `MATCHED_ADD_AVERAGE / 9` in each slot when that slot's own OBV bearish cross fires. This targets the same annual deployment budget as `$1,000/month` blind DCA.

## Selected Slots

| Slot | Index Source | Rank | Ticker | Name |
|---|---|---:|---|---|
| SPY_1_NVDA | S&P 500 / SPY | 1 | NVDA | NVIDIA Corporation |
| SPY_2_AAPL | S&P 500 / SPY | 2 | AAPL | Apple Inc. |
| SPY_3_MSFT | S&P 500 / SPY | 3 | MSFT | Microsoft Corporation |
| QQQ_1_NVDA | Nasdaq-100 / QQQ | 1 | NVDA | NVIDIA Corporation |
| QQQ_2_AAPL | Nasdaq-100 / QQQ | 2 | AAPL | Apple Inc. |
| QQQ_3_MSFT | Nasdaq-100 / QQQ | 3 | MSFT | Microsoft Corporation |
| DIA_1_GS | Dow / DIA | 1 | GS | Goldman Sachs Group |
| DIA_2_CAT | Dow / DIA | 2 | CAT | Caterpillar Inc. |
| DIA_3_MSFT | Dow / DIA | 3 | MSFT | Microsoft Corporation |

## Leaderboard

| Rank | Variant | OBV SMA | Avg Crosses / Slot / Yr | Matched Add Avg | Slot Add | Ending Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | monthly_blind_top9 |  |  |  |  | $2,232,968 | $2,099,968 | 1578.92% | $-490,645 | 4.28 | 100.0% | $0 |
| 2 | obv_bear_sma50_top9 | 50 | 10.96 | $1,095 | $122 | $1,725,774 | $1,592,774 | 1197.57% | $-370,239 | 4.30 | 89.9% | $10,942 |
| 3 | obv_bear_sma20_top9 | 20 | 17.51 | $685 | $76 | $1,705,104 | $1,572,104 | 1182.03% | $-362,908 | 4.33 | 92.6% | $6,906 |
| 4 | obv_bear_sma100_top9 | 100 | 7.01 | $1,712 | $190 | $1,394,599 | $1,261,599 | 948.57% | $-290,396 | 4.34 | 83.9% | $11,919 |
| 5 | obv_bear_sma150_top9 | 150 | 5.64 | $2,129 | $237 | $869,910 | $736,910 | 554.07% | $-166,754 | 4.42 | 75.7% | $19,678 |
| 6 | obv_bear_sma200_top9 | 200 | 4.98 | $2,410 | $268 | $703,667 | $570,667 | 429.07% | $-126,272 | 4.52 | 74.5% | $23,066 |
| 7 | obv_bear_sma252_top9 | 252 | 3.87 | $3,102 | $345 | $627,694 | $494,694 | 371.95% | $-106,952 | 4.63 | 73.4% | $36,474 |
| 8 | obv_bear_sma504_top9 | 504 | 1.60 | $7,519 | $835 | $530,766 | $397,766 | 299.07% | $-89,778 | 4.43 | 48.8% | $33,294 |

## Read

- Best OBV portfolio row is **SMA50** at **$1,725,774**, versus blind monthly top-nine DCA at **$2,232,968**. Difference: **$-507,194**.
- Closest tested cadence to 5 crosses/slot/year is **SMA200** at **4.98 crosses/slot/year**, with **$2,410** matched-add average and **$268** per slot signal.
- Because the top SPY and QQQ holdings currently overlap, this is not a diversified nine-company study; it is a nine-slot index-overlap study. That concentration is intentional for this pass.

## Best OBV Slot Breakdown

| Slot | Ticker | Crosses / Yr | Buys | Avg Buy | Ending Equity | Net | Ending Cash |
|---|---|---:|---:|---:|---:|---:|---:|
| DIA_1_GS | GS | 9.64 | 106 | $122 | $55,574 | $40,796 | $1,881 |
| DIA_2_CAT | CAT | 8.64 | 95 | $122 | $82,048 | $67,270 | $3,229 |
| DIA_3_MSFT | MSFT | 12.73 | 122 | $116 | $54,395 | $39,618 | $641 |
| QQQ_1_NVDA | NVDA | 10.18 | 112 | $121 | $646,726 | $631,948 | $1,198 |
| QQQ_2_AAPL | AAPL | 10.91 | 117 | $120 | $65,757 | $50,979 | $757 |
| QQQ_3_MSFT | MSFT | 12.73 | 122 | $116 | $54,395 | $39,618 | $641 |
| SPY_1_NVDA | NVDA | 10.18 | 112 | $121 | $646,726 | $631,948 | $1,198 |
| SPY_2_AAPL | AAPL | 10.91 | 117 | $120 | $65,757 | $50,979 | $757 |
| SPY_3_MSFT | MSFT | 12.73 | 122 | $116 | $54,395 | $39,618 | $641 |

## Charts

- Equity leaderboard: [`charts/equity_leaderboard.png`](charts/equity_leaderboard.png)
- Frequency/add sizing: [`charts/frequency_add_by_ma.png`](charts/frequency_add_by_ma.png)

## Outputs

- `leaderboard.csv`
- `daily_equity.csv`
- `slot_summary.csv`
- `selected_slots.csv`
