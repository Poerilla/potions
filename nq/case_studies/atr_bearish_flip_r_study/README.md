# NQ ATR Bearish Flip R Study

Question: after a bullish-to-bearish ATR Supertrend flip, if the flip close is the short reference price and the initial bearish ATR stop is the fixed stop, how often does price reach 1R, 2R, or 3R before touching that original stop?

Rules:
- ATR Supertrend-style stop: ATR(14) x 3.
- Short reference price is the flip bar close.
- Fixed stop is the initial bearish ATR stop on the flip bar.
- Path evaluation starts on the next daily bar after the flip is confirmed.
- If stop and target are both inside the same daily bar, the study counts it as stop-first.
- MAE is reported as adverse points/dollars for the short; negative values are worse.

## Summary

| Signal TF | R Target | Flips | Hits | Hit Rate | Stop-First Ambiguous | Avg Risk Pts | Avg ATR % | Hit Avg MAE | Hit Worst MAE | All Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| daily | 1R | 76 | 30 | 39.47% | 0 | 465.66 | 1.45% | -140.53 pts ($-2,810) | -847.75 pts ($-16,955) | -1580.25 pts ($-31,605) |
| daily | 2R | 76 | 15 | 19.74% | 0 | 465.66 | 1.45% | -162.62 pts ($-3,252) | -847.75 pts ($-16,955) | -1580.25 pts ($-31,605) |
| daily | 3R | 76 | 10 | 13.16% | 0 | 465.66 | 1.45% | -204.30 pts ($-4,086) | -847.75 pts ($-16,955) | -1580.25 pts ($-31,605) |
| weekly | 1R | 12 | 3 | 25.00% | 0 | 1160.21 | 3.85% | -650.75 pts ($-13,015) | -857.75 pts ($-17,155) | -3087.25 pts ($-61,745) |
| weekly | 2R | 12 | 0 | 0.00% | 0 | 1160.21 | 3.85% | +0.00 pts ($+0) | +0.00 pts ($+0) | -3087.25 pts ($-61,745) |
| weekly | 3R | 12 | 0 | 0.00% | 0 | 1160.21 | 3.85% | +0.00 pts ($+0) | +0.00 pts ($+0) | -3087.25 pts ($-61,745) |

## Read

Weekly ATR produced fewer bearish flips, with hit-rate deltas vs daily of -14.47 pts at 1R, -19.74 pts at 2R, and -13.16 pts at 3R.

## Daily Flip Split By Confirmed Weekly ATR State

| Weekly ATR State | R Target | Daily Flips | Hits | Hit Rate | Avg Risk Pts | Hit Avg MAE | Hit Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| down | 1R | 15 | 5 | 33.33% | 552.83 | -230.15 | -428.00 |
| down | 2R | 15 | 2 | 13.33% | 552.83 | -174.75 | -314.75 |
| down | 3R | 15 | 1 | 6.67% | 552.83 | -314.75 | -314.75 |
| up | 1R | 61 | 25 | 40.98% | 444.23 | -122.60 | -847.75 |
| up | 2R | 61 | 13 | 21.31% | 444.23 | -160.75 | -847.75 |
| up | 3R | 61 | 9 | 14.75% | 444.23 | -192.03 | -847.75 |

CSV outputs:
- `flip_targets.csv`: one row per flip/R target.
- `summary.csv`: aggregate hit rates and MAE.
- `daily_weekly_context_summary.csv`: daily flips split by already-confirmed weekly ATR state.
