# GOOGL / QQQ Overbought Deferral Filter Comparison

Data: Yahoo adjusted daily OHLCV.

Window: **2004-08-19 through 2026-06-03**.

Rule:

- Start with the same `$1,000/month` DCA contribution.
- If the filter is overbought on the first trading day of the month, skip that buy and leave the cash idle.
- Later allowed buys can spend up to **2.0x** the normal monthly amount.
- Daily filters are causal: the buy decision uses the prior completed daily bar. RSI weekly/monthly uses the prior completed weekly/monthly bar.

Filter families:

- **RSI:** smoothed RSI(14) EMA(14), same as the current RSI deferral study.
- **OBV:** daily OBV z-score above its moving average, plus simple OBV-above-MA diagnostics.
- **ATR:** adjusted close stretched above SMA50/SMA200 by ATR(14) units.

## Baselines

| Ticker | Ending Equity | Net | Max DD | Net/DD | Total Contributed |
|---|---:|---:|---:|---:|---:|
| GOOGL | $4,802,541 | $4,539,541 | $-934,019 | 4.86 | $263,000 |
| QQQ | $2,728,556 | $2,465,556 | $-478,448 | 5.15 | $263,000 |

## Best By Filter Family

| Ticker | Family | Filter | Detail | Ending Equity | vs Basic DCA | Gross Saved | Blocked | Redeployed Est. | Ending Cash | Deployed | Buys | Max DD | Net/DD |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | RSI | RSI monthly >=70 | RSI14 EMA14, prior monthly bar | $4,944,145 | $141,604 | $46,000 | 46 | $41,000 | $5,000 | 98.1% | 217 | $-961,379 | 4.87 |
| GOOGL | OBV | OBV z200 >=2.0 | daily OBV z-score vs SMA200 | $4,831,272 | $28,731 | $29,000 | 29 | $29,000 | $0 | 100.0% | 234 | $-939,484 | 4.86 |
| GOOGL | ATR | ATR stretch SMA50 >=4 | (close - SMA50) / ATR14 | $4,791,348 | $-11,193 | $36,000 | 36 | $36,000 | $0 | 100.0% | 227 | $-931,462 | 4.86 |
| QQQ | OBV | OBV z200 >=2.0 | daily OBV z-score vs SMA200 | $2,729,639 | $1,083 | $32,000 | 32 | $32,000 | $0 | 100.0% | 231 | $-478,801 | 5.15 |
| QQQ | RSI | RSI daily >=70 | RSI14 EMA14, prior daily bar | $2,729,320 | $764 | $13,000 | 13 | $12,000 | $1,000 | 99.6% | 250 | $-478,602 | 5.15 |
| QQQ | ATR | ATR stretch SMA50 >=5 | (close - SMA50) / ATR14 | $2,728,705 | $150 | $23,000 | 23 | $21,000 | $2,000 | 99.2% | 240 | $-478,560 | 5.15 |

## Top Rows

| Ticker | Family | Filter | Detail | Ending Equity | vs Basic DCA | Gross Saved | Blocked | Redeployed Est. | Ending Cash | Deployed | Buys | Max DD | Net/DD |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | RSI | RSI monthly >=70 | RSI14 EMA14, prior monthly bar | $4,944,145 | $141,604 | $46,000 | 46 | $41,000 | $5,000 | 98.1% | 217 | $-961,379 | 4.87 |
| GOOGL | OBV | OBV z200 >=2.0 | daily OBV z-score vs SMA200 | $4,831,272 | $28,731 | $29,000 | 29 | $29,000 | $0 | 100.0% | 234 | $-939,484 | 4.86 |
| GOOGL | RSI | RSI weekly >=75 | RSI14 EMA14, prior weekly bar | $4,813,174 | $10,633 | $8,000 | 8 | $8,000 | $0 | 100.0% | 255 | $-935,717 | 4.86 |
| GOOGL | OBV | OBV z50 >=1.0 | daily OBV z-score vs SMA50 | $4,806,402 | $3,861 | $92,000 | 92 | $89,000 | $3,000 | 98.9% | 171 | $-933,811 | 4.87 |
| GOOGL | RSI | RSI weekly >=80 | RSI14 EMA14, prior weekly bar | $4,802,541 | $0 | $0 | 0 | $0 | $0 | 100.0% | 263 | $-934,019 | 4.86 |
| GOOGL | RSI | RSI monthly >=80 | RSI14 EMA14, prior monthly bar | $4,802,541 | $0 | $0 | 0 | $0 | $0 | 100.0% | 263 | $-934,019 | 4.86 |
| GOOGL | RSI | RSI monthly >=75 | RSI14 EMA14, prior monthly bar | $4,800,714 | $-1,827 | $9,000 | 9 | $9,000 | $0 | 100.0% | 254 | $-933,663 | 4.86 |
| GOOGL | OBV | OBV z100 >=1.5 | daily OBV z-score vs SMA100 | $4,798,770 | $-3,771 | $54,000 | 54 | $54,000 | $0 | 100.0% | 209 | $-932,727 | 4.86 |
| GOOGL | ATR | ATR stretch SMA50 >=4 | (close - SMA50) / ATR14 | $4,791,348 | $-11,193 | $36,000 | 36 | $36,000 | $0 | 100.0% | 227 | $-931,462 | 4.86 |
| GOOGL | ATR | ATR stretch SMA50 >=5 | (close - SMA50) / ATR14 | $4,790,305 | $-12,236 | $25,000 | 25 | $25,000 | $0 | 100.0% | 238 | $-931,633 | 4.86 |
| GOOGL | OBV | OBV z50 >=1.5 | daily OBV z-score vs SMA50 | $4,790,127 | $-12,414 | $52,000 | 52 | $51,000 | $1,000 | 99.6% | 211 | $-931,029 | 4.86 |
| GOOGL | OBV | OBV z200 >=1.5 | daily OBV z-score vs SMA200 | $4,789,549 | $-12,991 | $57,000 | 57 | $54,000 | $3,000 | 98.9% | 206 | $-930,160 | 4.87 |
| QQQ | OBV | OBV z200 >=2.0 | daily OBV z-score vs SMA200 | $2,729,639 | $1,083 | $32,000 | 32 | $32,000 | $0 | 100.0% | 231 | $-478,801 | 5.15 |
| QQQ | RSI | RSI daily >=70 | RSI14 EMA14, prior daily bar | $2,729,320 | $764 | $13,000 | 13 | $12,000 | $1,000 | 99.6% | 250 | $-478,602 | 5.15 |
| QQQ | RSI | RSI weekly >=75 | RSI14 EMA14, prior weekly bar | $2,728,735 | $179 | $2,000 | 2 | $2,000 | $0 | 100.0% | 261 | $-478,481 | 5.15 |
| QQQ | ATR | ATR stretch SMA50 >=5 | (close - SMA50) / ATR14 | $2,728,705 | $150 | $23,000 | 23 | $21,000 | $2,000 | 99.2% | 240 | $-478,560 | 5.15 |
| QQQ | RSI | RSI daily >=80 | RSI14 EMA14, prior daily bar | $2,728,556 | $0 | $0 | 0 | $0 | $0 | 100.0% | 263 | $-478,448 | 5.15 |
| QQQ | RSI | RSI weekly >=80 | RSI14 EMA14, prior weekly bar | $2,728,556 | $0 | $0 | 0 | $0 | $0 | 100.0% | 263 | $-478,448 | 5.15 |
| QQQ | RSI | RSI monthly >=80 | RSI14 EMA14, prior monthly bar | $2,728,556 | $0 | $0 | 0 | $0 | $0 | 100.0% | 263 | $-478,448 | 5.15 |
| QQQ | RSI | RSI daily >=75 | RSI14 EMA14, prior daily bar | $2,728,468 | $-87 | $1,000 | 1 | $1,000 | $0 | 100.0% | 262 | $-478,432 | 5.15 |
| QQQ | OBV | OBV z100 >=2.0 | daily OBV z-score vs SMA100 | $2,728,337 | $-219 | $20,000 | 20 | $20,000 | $0 | 100.0% | 243 | $-478,407 | 5.15 |
| QQQ | OBV | OBV z50 >=2.0 | daily OBV z-score vs SMA50 | $2,728,101 | $-455 | $13,000 | 13 | $13,000 | $0 | 100.0% | 250 | $-478,295 | 5.15 |
| QQQ | OBV | OBV z50 >=1.5 | daily OBV z-score vs SMA50 | $2,726,092 | $-2,464 | $52,000 | 52 | $52,000 | $0 | 100.0% | 211 | $-477,971 | 5.15 |
| QQQ | RSI | RSI daily >=65 | RSI14 EMA14, prior daily bar | $2,725,581 | $-2,975 | $55,000 | 55 | $53,000 | $2,000 | 99.2% | 208 | $-478,081 | 5.15 |

## Read

- **GOOGL RSI monthly >=70:** saved **$46,000** across **46** blocked months, redeployed about **$41,000**, left **$5,000** cash, and finished **$141,604** versus basic DCA.
- **GOOGL best OBV / ATR:** OBV tops at **OBV z200 >=2.0** (**$28,731** vs basic), ATR tops at **ATR stretch SMA50 >=4** (**$-11,193** vs basic). Overall best tested row is **RSI monthly >=70** at **$4,944,145** (**$141,604** vs basic).
- **QQQ RSI monthly >=70:** saved **$75,000** across **75** blocked months, redeployed about **$66,000**, left **$9,000** cash, and finished **$-80,549** versus basic DCA.
- **QQQ best OBV / ATR:** OBV tops at **OBV z200 >=2.0** (**$1,083** vs basic), ATR tops at **ATR stretch SMA50 >=5** (**$150** vs basic). Overall best tested row is **OBV z200 >=2.0** at **$2,729,639** (**$1,083** vs basic).

## Charts

- GOOGL: [`charts/googl_filter_comparison.png`](charts/googl_filter_comparison.png)
- QQQ: [`charts/qqq_filter_comparison.png`](charts/qqq_filter_comparison.png)

## Files

- `summary.csv`
- `baselines.csv`
- `events.csv`
- `selected_curves.csv`
