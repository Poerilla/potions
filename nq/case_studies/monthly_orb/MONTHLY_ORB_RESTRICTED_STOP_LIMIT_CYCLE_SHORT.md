# NQ Monthly ORB Restricted Stop-Limit Cycle Short

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

Dollar figures use NQ point value of $20/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 377 | -4,954.6 | $-99,092 | $-229,472 | 40.8% | 0.92 | 108.6 | 847.0 |

## Entry Type Split

| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Bottom-Refill | 106 | 1,962.6 | $39,252 | $-24,830 | 50.9% | 1.30 |
| Stop-Breakdown | 223 | 1,885.8 | $37,715 | $-163,050 | 40.4% | 1.04 |
| Top-Limit | 48 | -8,803.0 | $-176,060 | $-176,060 | 20.8% | 0.27 |

## Exit Mix

- Daily-Close-25pct-Back-In-Range-Before-TP1: **52**
- False-Breakdown-Close-25pct-Inside: **50**
- Daily-Close-At-Or-Above-Range-Low-Before-TP1: **46**
- Top-Limit-Daily-Close-SL: **36**
- TP50+TP1+Daily-Close-25pct-Back-In-Range-After-TP1: **31**
- TP50+TP1+TP2: **29**
- TP50+Daily-Close-25pct-Back-In-Range-Before-TP1: **29**
- TP50+Daily-Close-At-Or-Above-Range-Low-Before-TP1: **27**
- TP50+TP1: **26**
- TP50+TP1+Period-Close: **19**
- Period-Close: **13**
- TP50+Period-Close: **11**
- Bottom-Boundary+TP1: **5**
- Bottom-Boundary+Top-Limit-Daily-Close-SL: **3**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 5 | 85.2 | 3 | 2 | 42.8 | 69.5 |
| 2011 | 30 | -465.0 | 14 | 16 | 32.7 | 78.8 |
| 2012 | 24 | 720.0 | 12 | 12 | 25.9 | 60.8 |
| 2013 | 34 | -860.1 | 11 | 23 | 30.1 | 77.2 |
| 2014 | 37 | 79.0 | 16 | 21 | 32.8 | 85.2 |
| 2015 | 39 | 75.4 | 21 | 17 | 43.2 | 120.8 |
| 2016 | 27 | 167.0 | 12 | 15 | 52.5 | 137.0 |
| 2017 | 26 | -745.4 | 9 | 17 | 50.3 | 130.5 |
| 2018 | 21 | 1,090.2 | 12 | 9 | 81.4 | 269.0 |
| 2019 | 12 | -968.8 | 4 | 8 | 87.6 | 150.0 |
| 2020 | 15 | 155.8 | 4 | 11 | 197.5 | 362.2 |
| 2021 | 11 | -3,611.0 | 2 | 9 | 201.3 | 569.2 |
| 2022 | 25 | 5,955.8 | 12 | 13 | 233.8 | 598.5 |
| 2023 | 29 | -3,900.4 | 10 | 19 | 158.8 | 406.8 |
| 2024 | 14 | -4,040.6 | 2 | 12 | 304.4 | 432.8 |
| 2025 | 22 | 184.0 | 7 | 15 | 385.4 | 847.0 |
| 2026 | 6 | 1,124.2 | 3 | 3 | 223.9 | 388.2 |

## Outputs

- `nq/nq_monthly_orb_restricted_stop_limit_cycle_short.csv`
- `nq/nq_monthly_orb_restricted_stop_limit_cycle_short_events.csv`
- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle_short/INDEX.md`
