# EURUSD hourly ST day-bias DCA

Prev-day hourly ST ≥70% bull/bear sets next-day bias. Enter 0.5 lot at prev-day
pullback fraction f (50/40/30%), SL at prev-day extreme. DCA up to 5×/month,
one entry per day. Exit on lot SL or period end (week=Fri close / month=month-end).

Unit = 0.5 lot (PV $50k), fee $0.75/half-lot. Window 2015-01-01 → 2026-03-31.

Bias day counts: bull **1180** / bear **1352** / flat **981**.

| Strategy | f | Period | Net | Closed DD | Net/DD | Camps | Lots | WR | Entry days | Opp days |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| st_daybias_dca_f30_week | 30% | week | $-4,073 | $-9,637 | -0.42 | 620 | 675.0 | 15.5% | 675 | 2531 |
| st_daybias_dca_f30_month | 30% | month | $-13,036 | $-15,889 | -0.82 | 555 | 674.0 | 11.3% | 674 | 2531 |

Opp days = sessions with a clear 70% ST bias from the prior day.
Entry days = days that actually filled an add (touch of f-level).

CSV: `leaderboard.csv`
