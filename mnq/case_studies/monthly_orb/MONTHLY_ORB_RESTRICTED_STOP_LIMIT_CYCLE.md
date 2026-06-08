# MNQ Monthly ORB Restricted Stop-Limit Cycle

Rules modeled:

- Long only. `--allow-short` exists as a reserved flag but raises `NotImplementedError`.
- Monthly OR = first 3 daily rows of each calendar month.
- Primary order = buy stop at the OR high after the OR forms.
- If the stop fills but the same daily candle closes more than 25% back inside the OR, close all 3 contracts at that close and re-arm the stop.
- Confirmed breakout packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner at TP2.
- If a confirmed breakout package closes more than 25% back inside the OR before TP1, close all at the daily close and arm a bottom-boundary limit.
- Top-boundary refill packages still close before TP1 on any daily close at or below the OR high.
- After any TP1 success, arm a 2-contract top-boundary refill at the OR high, even if an earlier runner is still open.
- Top-boundary refills take 1 off halfway to TP1 and 1 off at TP1; they do not leave a runner.
- Bottom-boundary limit enters at the OR low, exits only on a daily close below `OR low - 0.25 * range`, takes 1 off at the OR high, and takes the other 2 off at TP1.
- After a failed breakout before TP1, the bottom-boundary limit becomes available, but a fresh stop-breakout can still fire before that bottom limit fills.
- Primary 3-contract packages remain mutually exclusive. A 2-contract top-boundary refill may overlap with an earlier runner.

Daily OHLC caveat: this cannot prove intraday ordering. The report uses the same daily data family as the older monthly restricted studies.

Dollar figures use MNQ point value of $2/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 148 | 25,644.0 | $51,288 | $-13,144 | 52.0% | 1.63 | 213.2 | 1,039.2 |

## Entry Type Split

| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Bottom-Limit | 17 | 9,206.2 | $18,412 | $-2,522 | 52.9% | 3.04 |
| Stop-Breakout | 101 | 14,202.6 | $28,405 | $-16,464 | 48.5% | 1.43 |
| Top-Refill | 30 | 2,235.1 | $4,470 | $-2,755 | 63.3% | 1.67 |

## Exit Mix

- Daily-Close-25pct-Back-In-Range-Before-TP1: **27**
- TP50+TP1+TP2: **22**
- TP50+TP1+Period-Close: **13**
- TP50+Daily-Close-25pct-Back-In-Range-Before-TP1: **13**
- False-Breakout-Close-25pct-Inside: **12**
- TP50+TP1: **11**
- Daily-Close-At-Or-Below-Range-High-Before-TP1: **11**
- TP50+TP1+Daily-Close-25pct-Back-In-Range-After-TP1: **9**
- TP50+Daily-Close-At-Or-Below-Range-High-Before-TP1: **8**
- Bottom-Limit-Daily-Close-SL: **7**
- TP50+Period-Close: **5**
- Top-Boundary+TP1: **4**
- Top-Boundary+Period-Close: **3**
- Period-Close: **2**
- Top-Boundary+Bottom-Limit-Daily-Close-SL: **1**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 11 | 3,977.0 | 9 | 2 | 69.4 | 118.8 |
| 2020 | 29 | 8,231.4 | 18 | 11 | 175.2 | 559.0 |
| 2021 | 28 | 4,587.0 | 15 | 13 | 159.1 | 369.2 |
| 2022 | 15 | -645.5 | 6 | 9 | 370.9 | 810.0 |
| 2023 | 18 | 5,057.5 | 9 | 9 | 167.7 | 401.2 |
| 2024 | 18 | 6,966.6 | 11 | 7 | 200.3 | 577.8 |
| 2025 | 21 | 1,232.0 | 7 | 14 | 304.6 | 1039.2 |
| 2026 | 8 | -3,762.0 | 2 | 6 | 334.6 | 601.5 |

## Outputs

- `mnq/mnq_monthly_orb_restricted_stop_limit_cycle.csv`
- `mnq/mnq_monthly_orb_restricted_stop_limit_cycle_events.csv`
- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle/INDEX.md`
