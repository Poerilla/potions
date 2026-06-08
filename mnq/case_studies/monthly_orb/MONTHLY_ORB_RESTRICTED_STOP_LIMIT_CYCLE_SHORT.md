# MNQ Monthly ORB Restricted Stop-Limit Cycle Short

Rules modeled:

- Short only. This is a separate bearish mirror of the long restricted stop-limit cycle.
- Monthly OR = first 3 daily rows of each calendar month.
- Primary order = sell stop at the OR low after the OR forms.
- If the stop fills but the same daily candle closes more than 25% back inside the OR, close all 3 contracts at that close and re-arm the sell stop.
- Confirmed breakdown packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner at TP2.
- If a confirmed breakdown package closes more than 25% back inside the OR before TP1, close all at the daily close and arm a top-boundary limit.
- Bottom-boundary refill packages close before TP1 on any daily close at or above the OR low.
- After any TP1 success, arm a 2-contract bottom-boundary refill at the OR low, even if an earlier runner is still open.
- Bottom-boundary refills take 1 off halfway to TP1 and 1 off at TP1; they do not leave a runner.
- Top-boundary limit enters at the OR high, exits only on a daily close above `OR high + 0.25 * range`, takes 1 off at the OR low, and takes the other 2 off at TP1.
- After a failed breakdown before TP1, the top-boundary limit becomes available, but a fresh sell-stop breakdown can still fire before that top limit fills.

Daily OHLC caveat: this cannot prove intraday ordering. This short study inherits the same daily data limitations as the long version.

Dollar figures use MNQ point value of $2/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 130 | -3,840.1 | $-7,680 | $-23,710 | 33.8% | 0.92 | 234.9 | 844.8 |

## Entry Type Split

| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Bottom-Refill | 23 | 1,550.6 | $3,101 | $-2,469 | 39.1% | 1.37 |
| Stop-Breakdown | 90 | 2,658.2 | $5,316 | $-17,065 | 36.7% | 1.08 |
| Top-Limit | 17 | -8,049.0 | $-16,098 | $-16,098 | 11.8% | 0.14 |

## Exit Mix

- Daily-Close-25pct-Back-In-Range-Before-TP1: **23**
- False-Breakdown-Close-25pct-Inside: **21**
- Top-Limit-Daily-Close-SL: **15**
- Daily-Close-At-Or-Above-Range-Low-Before-TP1: **13**
- TP50+Daily-Close-25pct-Back-In-Range-Before-TP1: **13**
- TP50+TP1+TP2: **12**
- TP50+TP1+Period-Close: **8**
- TP50+TP1+Daily-Close-25pct-Back-In-Range-After-TP1: **7**
- Period-Close: **5**
- TP50+TP1: **5**
- TP50+Daily-Close-At-Or-Above-Range-Low-Before-TP1: **4**
- TP50+Period-Close: **3**
- Bottom-Boundary+TP1: **1**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 8 | 746.8 | 4 | 4 | 91.2 | 139.2 |
| 2020 | 15 | 97.5 | 4 | 11 | 198.2 | 361.5 |
| 2021 | 11 | -3,628.8 | 2 | 9 | 202.5 | 570.8 |
| 2022 | 25 | 5,957.6 | 12 | 13 | 233.6 | 589.8 |
| 2023 | 29 | -4,286.1 | 10 | 19 | 160.9 | 404.2 |
| 2024 | 14 | -4,031.4 | 2 | 12 | 304.4 | 433.5 |
| 2025 | 22 | 181.5 | 7 | 15 | 385.0 | 844.8 |
| 2026 | 6 | 1,122.8 | 3 | 3 | 228.5 | 388.0 |

## Outputs

- `mnq/mnq_monthly_orb_restricted_stop_limit_cycle_short.csv`
- `mnq/mnq_monthly_orb_restricted_stop_limit_cycle_short_events.csv`
- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle_short/INDEX.md`
