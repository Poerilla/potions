# MES ATR Supertrend Equity Scaling (ES Price Proxy)

MES local DBN was corrupt, so this uses ES daily and ES 15:50 1-minute add prices as the price proxy with MES point value ($5/pt). Strategy logic is comparable because MES and ES track the same index; liquidity, commission, and slippage must still be validated on MES/MES1! in TradingView/Tradovate.

Rule: at each calendar-year start, choose the largest bump level where current capital is at least **3x the full-sample MTM DD** for that bump level. Level 0 is the 10-max fixed study. Level 1 bumps every scale event by one contract and max stack from 10 to 11.

Run note: `--max-bump 40`, so largest allowed stack is 50.

## Summary

| Variant | Base Net | Base MTM DD | Base PF | Start Capital | End Capital | Dynamic Net | Dynamic MTM DD | End/Start | Peak Bump | Peak Max Contracts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Weekly primary, 3-initial | $129,439 | $-32,244 | 5.01 | $96,731 | $96,248 | $-484 | $-6,518 | 0.99x | 0 | 10 |
| Weekly primary, ladder 1/1/2/2/2 | $125,192 | $-33,336 | 4.74 | $100,009 | $99,580 | $-429 | $-6,216 | 1.00x | 0 | 10 |

## Yearly Tables

### Weekly primary, 3-initial

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | $96,731 | 0 | 10 | $96,731 | $0 | $0 | $0 | 0 | $96,731 |
| 2011 | $96,731 | 0 | 10 | $96,731 | $0 | $0 | $0 | 0 | $96,731 |
| 2012 | $96,731 | 0 | 10 | $96,731 | $0 | $-484 | $-6,518 | 10 | $96,248 |
| 2013 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2014 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2015 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2016 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2017 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2018 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2019 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2020 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2021 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2022 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2023 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2024 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2025 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |
| 2026 | $96,248 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $96,248 |

### Weekly primary, ladder 1/1/2/2/2

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | $100,009 | 0 | 10 | $100,009 | $0 | $0 | $0 | 0 | $100,009 |
| 2011 | $100,009 | 0 | 10 | $100,009 | $0 | $0 | $0 | 0 | $100,009 |
| 2012 | $100,009 | 0 | 10 | $100,009 | $0 | $-429 | $-6,216 | 10 | $99,580 |
| 2013 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2014 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2015 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2016 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2017 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2018 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2019 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2020 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2021 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2022 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2023 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2024 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2025 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
| 2026 | $99,580 | NO_TRADE | 0 |  |  | $0 | $0 | 0 | $99,580 |
