# f30 week — wider SL: session extreme ± p·ATR

## What the charts used as “previous day extreme”

Charts / original research used the **prior NY date that has bars** in the
day table (consecutive groupby). For **Mondays that is often Sunday**
(582/587 Mondays in-sample) — a thin/partial session, not Friday’s full range.

**Fix here:** previous session = prior Mon–Fri day with bars (Sun/Sat skipped → Friday).

## Stop definition

```
long  stop = prev_session_low  - p * hourly_ATR(14)
short stop = prev_session_high + p * hourly_ATR(14)
```

Entry still at 30% pullback of that same session range. Bias still from
prior calendar day’s ST fraction (unchanged).

Would-be-winner set (n=41): p_need median=0.49, p95=2.38, p_max=2.79 (session prev). p*=2.80 clears all.

## Sweep (pandas, break-fixed, session prev)

| Strategy | p | Net | Closed DD | Net/DD | WR | Med hold | Stops | Period |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| f30_week_sess_sl_p0.00atr | 0.00 | $-4,145 | $-10,489 | -0.40 | 21.6% | 6.8 | 431 | 156 |
| f30_week_sess_sl_p1.50atr | 1.50 | $-9,411 | $-13,587 | -0.69 | 30.9% | 22.0 | 308 | 235 |
| f30_week_sess_sl_p0.50atr | 0.50 | $-10,673 | $-16,805 | -0.64 | 23.6% | 9.3 | 388 | 183 |
| f30_week_sess_sl_p2.00atr | 2.00 | $-13,956 | $-21,109 | -0.66 | 32.5% | 25.8 | 286 | 252 |
| f30_week_sess_sl_p1.00atr | 1.00 | $-18,668 | $-22,589 | -0.83 | 26.1% | 13.7 | 356 | 203 |
| f30_week_sess_sl_p3.00atr | 3.00 | $-24,078 | $-30,065 | -0.80 | 35.2% | 31.3 | 252 | 282 |
| f30_week_sess_sl_p2.50atr | 2.50 | $-24,146 | $-28,071 | -0.86 | 33.5% | 28.2 | 272 | 263 |
| f30_week_sess_sl_p2.80atr | 2.80 | $-24,247 | $-29,792 | -0.81 | 34.6% | 30.3 | 260 | 275 |

p* = **2.8** is the smallest round value that keeps all 41 would-be-winner
paths alive to Friday given session-prev extremes (from MAE/ATR analysis).

CSV: `leaderboard.csv` · requirements: `../eurusd_st_daybias_f30_close_sl/p_atr_wouldbe_requirements.csv`
