# NQ Monthly ORB Restricted Stop-Limit Cycle

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

Dollar figures use NQ point value of $20/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 338 | 30,646.8 | $612,935 | $-139,060 | 49.1% | 1.58 | 120.0 | 1,038.0 |

## Entry Type Split

| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Bottom-Limit | 40 | 8,135.8 | $162,715 | $-35,950 | 35.0% | 2.19 |
| Stop-Breakout | 238 | 19,741.0 | $394,820 | $-164,675 | 48.3% | 1.47 |
| Top-Refill | 60 | 2,770.0 | $55,400 | $-27,468 | 61.7% | 1.71 |

## Exit Mix

- Daily-Close-25pct-Back-In-Range-Before-TP1: **61**
- TP50+TP1+TP2: **49**
- TP50+TP1+Period-Close: **34**
- False-Breakout-Close-25pct-Inside: **34**
- TP50+Daily-Close-25pct-Back-In-Range-Before-TP1: **25**
- Bottom-Limit-Daily-Close-SL: **24**
- Daily-Close-At-Or-Below-Range-High-Before-TP1: **22**
- TP50+Daily-Close-At-Or-Below-Range-High-Before-TP1: **19**
- TP50+TP1: **18**
- TP50+TP1+Daily-Close-25pct-Back-In-Range-After-TP1: **17**
- TP50+Period-Close: **16**
- Period-Close: **7**
- Top-Boundary+TP1: **6**
- Top-Boundary+Period-Close: **4**
- Top-Boundary+Bottom-Limit-Daily-Close-SL: **2**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 10 | 165.5 | 5 | 5 | 53.7 | 113.2 |
| 2011 | 22 | 19.2 | 12 | 10 | 36.9 | 119.2 |
| 2012 | 20 | 511.6 | 10 | 10 | 26.9 | 70.5 |
| 2013 | 26 | 563.1 | 12 | 14 | 29.5 | 86.0 |
| 2014 | 22 | 95.1 | 9 | 13 | 34.0 | 65.2 |
| 2015 | 21 | -410.9 | 6 | 15 | 47.6 | 130.0 |
| 2016 | 22 | -189.1 | 8 | 14 | 49.9 | 258.5 |
| 2017 | 23 | 1,518.1 | 15 | 8 | 40.3 | 217.8 |
| 2018 | 23 | -249.1 | 9 | 14 | 120.8 | 379.8 |
| 2019 | 16 | 6,181.2 | 13 | 3 | 89.1 | 272.8 |
| 2020 | 26 | 9,074.5 | 17 | 9 | 160.5 | 360.0 |
| 2021 | 28 | 4,589.6 | 15 | 13 | 158.9 | 369.5 |
| 2022 | 15 | -637.8 | 6 | 9 | 370.7 | 811.0 |
| 2023 | 17 | 5,330.4 | 9 | 8 | 170.9 | 401.0 |
| 2024 | 18 | 6,979.2 | 11 | 7 | 200.2 | 576.8 |
| 2025 | 21 | 874.4 | 7 | 14 | 311.0 | 1038.0 |
| 2026 | 8 | -3,768.5 | 2 | 6 | 340.1 | 602.0 |

## Outputs

- `nq/nq_monthly_orb_restricted_stop_limit_cycle.csv`
- `nq/nq_monthly_orb_restricted_stop_limit_cycle_events.csv`
- Charts: `case_studies/monthly_orb/restricted_stop_limit_cycle/INDEX.md`
