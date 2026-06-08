# MNQ Monthly ORB 4H Breakout Diagnostics

A breakout is counted when a 4-hour candle closes outside the monthly opening range after the first three trading sessions. Events are non-overlapping: after a breakout, the path is tracked until the opposing boundary, 2R, or month end.

Definitions:

- **False break:** opposing OR boundary trades before 1R target.
- **Clean 1R:** 1R target trades before any 4h close back inside the OR.
- **2R:** price reaches the 2R measured move before the opposing boundary.

- Total breakouts: **714**
- False breaks: **42** (5.9%)
- Hit 1R: **643** (90.1%)
- Clean 1R: **610** (85.4%)
- Hit 2R: **594** (83.2%)

| Direction | Breaks | False | Hit 1R | Clean 1R | Hit 2R | Avg MAE pts | Avg MFE pts |
|---|---:|---:|---:|---:|---:|---:|---:|
| Long | 505 | 23 | 462 | 441 | 431 | 97.5 | 110.5 |
| Short | 209 | 19 | 181 | 169 | 163 | 182.4 | 191.5 |

## Outputs

- `mnq/mnq_monthly_orb_4h_breakout_diagnostics.csv`
- `mnq/case_studies/monthly_orb/4h_breakout_diagnostics/clean_breaks/INDEX.md`
- `mnq/case_studies/monthly_orb/monthly_orb_yearly_range_lines/INDEX.md`
