# Monthly open ATR extension — pct75 lookback filter

Kitchen-sink predictors for months that reach the causal rolling-6m
**pct75** band (min + 0.75·(max−min)) after the opening week.
Diagnostic only — not a promotion gate.

## Base rates

| Market | N months | pct75 any | pct75 up | pct75 dn | max any |
|---|---:|---:|---:|---:|---:|
| NQ | 169 | 94.1% | 60.9% | 49.1% | 79.9% |

## Calendar month hit rates (pct75 any)

### NQ

| Month | N | Hit% | Lift |
|---|---:|---:|---:|
| Jan | 12 | 100% | 1.06x |
| Feb | 14 | 93% | 0.99x |
| Mar | 15 | 93% | 0.99x |
| Apr | 15 | 87% | 0.92x |
| May | 15 | 100% | 1.06x |
| Jun | 15 | 100% | 1.06x |
| Jul | 14 | 93% | 0.99x |
| Aug | 14 | 86% | 0.91x |
| Sep | 13 | 100% | 1.06x |
| Oct | 14 | 93% | 0.99x |
| Nov | 14 | 100% | 1.06x |
| Dec | 14 | 86% | 0.91x |

## Top lift predictors (pct75 any, lift≥1.15, n≥8, |z|≥1.0)

### NQ

_No strong lifts at this threshold._

## Protective / skip signals (lift≤0.85, true bucket)

### NQ

_None at this threshold._

## Forward weekly ATR-trail after touch months

| Touch label | Cohort | Outcome | N | Rate |
|---|---|---|---:|---:|
| touch_pct75_any | touch | fwd_weeks_toward_trail | 157 | 37% |
| touch_pct75_any | no_touch | fwd_weeks_toward_trail | 10 | 40% |
| touch_pct75_any | touch | fwd_weeks_away_trail | 157 | 37% |
| touch_pct75_any | no_touch | fwd_weeks_away_trail | 10 | 20% |
| touch_max_any | touch | fwd_weeks_toward_trail | 133 | 34% |
| touch_max_any | no_touch | fwd_weeks_toward_trail | 34 | 50% |
| touch_max_any | touch | fwd_weeks_away_trail | 133 | 39% |
| touch_max_any | no_touch | fwd_weeks_away_trail | 34 | 24% |

## Top pairwise combos (exploratory)

### NQ

| Combo | N | Hit% | Lift |
|---|---:|---:|---:|
| prior_vol_buildup AND prior_atr_reverted | 8 | 100% | 1.06x |
| prior_vol_buildup AND prior_bear | 17 | 100% | 1.06x |
| prior_vol_buildup AND swept_swing_high_6m | 9 | 100% | 1.06x |
| prior_atr_reverted AND prior_doji | 8 | 100% | 1.06x |
| prior_atr_reverted AND prior_bear | 12 | 100% | 1.06x |
| swept_swing_low_6m AND swept_swing_low_12m | 9 | 100% | 1.06x |
| swept_swing_low_6m AND prior_bear | 12 | 100% | 1.06x |
| prior_bear AND swept_swing_high_6m | 16 | 100% | 1.06x |

## Notes

- Band = causal rolling **6** prior months mean(min/med/max).
- Opening-week ORB is allowed (strategy already waits until after week 1).
- Swing sweeps / candle patterns / volume / ATR width use **prior completed** month only.
- Forward trail stats are consequences, not entry filters.
