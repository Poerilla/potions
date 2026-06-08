# MNQ Monthly ORB Daily-Close Breakout Diagnostics

A breakout is counted only when a daily candle closes outside the monthly opening range after the first three trading sessions. After that close is known, the script tracks later 4-hour candles through the rest of the month.

Definitions:

- **Clean 1R:** TP1 trades before any daily close back inside the OR and before any 4h candle trades back into the OR.
- **Wide-berth 1R:** TP1 trades before the opposing OR boundary, ignoring interim retests/closes.
- **False break:** opposing OR boundary trades before TP1.
- Same-bar ambiguity is conservative: an opposing-boundary touch before TP1 wins over TP1, and a range retest in the same 4h candle prevents a clean label.

- Total daily-close breakouts: **107**
- False breaks: **29** (27.1%)
- Wide-berth TP1 before opposing boundary: **63** (58.9%)
- Clean 1R: **36** (33.6%)
- Hit TP2: **30** (28.0%)
- Clean and hit TP2: **18** (16.8%)

| Direction | Breaks | False | Wide TP1 | Clean 1R | Hit TP2 | Clean+TP2 | Avg MAE pts | Avg MFE pts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Long | 68 | 19 | 41 | 22 | 20 | 12 | 329.9 | 403.8 |
| Short | 39 | 10 | 22 | 14 | 10 | 6 | 468.3 | 467.7 |

## Outputs

- `mnq/mnq_monthly_orb_daily_close_breakout_diagnostics.csv`
- `mnq/case_studies/monthly_orb/daily_close_breakout_diagnostics/clean_months/INDEX.md`
- `mnq/case_studies/monthly_orb/monthly_orb_yearly_range_lines/INDEX.md`
