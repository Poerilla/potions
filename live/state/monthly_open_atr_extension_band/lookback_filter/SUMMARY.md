# Monthly open ATR extension — pct75 lookback filter

Kitchen-sink predictors for months that reach the causal rolling-6m
**pct75** band (min + 0.75·(max−min)) after the opening week.
Diagnostic only — not a promotion gate.

## Base rates

| Market | N months | pct75 any | pct75 up | pct75 dn | max any |
|---|---:|---:|---:|---:|---:|
| NQ | 143 | 65.0% | 55.2% | 16.1% | 79.7% |
| US30 | 82 | 61.0% | 42.7% | 23.2% | 75.6% |
| YM | 144 | 59.7% | 45.8% | 18.8% | 75.7% |

## Calendar month hit rates (pct75 any)

### NQ

| Month | N | Hit% | Lift |
|---|---:|---:|---:|
| Jan | 11 | 73% | 1.12x |
| Feb | 14 | 57% | 0.88x |
| Mar | 13 | 77% | 1.18x |
| Apr | 11 | 45% | 0.70x |
| May | 13 | 69% | 1.06x |
| Jun | 11 | 73% | 1.12x |
| Jul | 10 | 90% | 1.38x |
| Aug | 12 | 67% | 1.03x |
| Sep | 10 | 50% | 0.77x |
| Oct | 12 | 75% | 1.15x |
| Nov | 13 | 69% | 1.06x |
| Dec | 13 | 38% | 0.59x |

### US30

| Month | N | Hit% | Lift |
|---|---:|---:|---:|
| Jan | 6 | 50% | 0.82x |
| Feb | 6 | 83% | 1.37x |
| Mar | 6 | 83% | 1.37x |
| Apr | 6 | 17% | 0.27x |
| May | 7 | 57% | 0.94x |
| Jun | 8 | 50% | 0.82x |
| Jul | 8 | 38% | 0.61x |
| Aug | 7 | 71% | 1.17x |
| Sep | 7 | 71% | 1.17x |
| Oct | 7 | 71% | 1.17x |
| Nov | 7 | 71% | 1.17x |
| Dec | 7 | 71% | 1.17x |

### YM

| Month | N | Hit% | Lift |
|---|---:|---:|---:|
| Jan | 11 | 73% | 1.22x |
| Feb | 11 | 64% | 1.07x |
| Mar | 13 | 62% | 1.03x |
| Apr | 13 | 46% | 0.77x |
| May | 14 | 36% | 0.60x |
| Jun | 12 | 67% | 1.12x |
| Jul | 12 | 58% | 0.98x |
| Aug | 12 | 50% | 0.84x |
| Sep | 12 | 50% | 0.84x |
| Oct | 12 | 67% | 1.12x |
| Nov | 11 | 73% | 1.22x |
| Dec | 11 | 82% | 1.37x |

## Top lift predictors (pct75 any, lift≥1.15, n≥8, |z|≥1.0)

### NQ

| Feature | Bucket | N | Hit% | Base% | Lift | Δpp | z |
|---|---|---:|---:|---:|---:|---:|---:|
| prior_vol_buildup | true | 20 | 95% | 65% | 1.46x | +30.0 | 4.76 |
| prior_atr_reverted | true | 16 | 94% | 65% | 1.44x | +28.7 | 3.96 |
| cal_month | 7 | 10 | 90% | 65% | 1.38x | +25.0 | 2.43 |
| month_name | Jul | 10 | 90% | 65% | 1.38x | +25.0 | 2.43 |
| prior_atr_wide | true | 14 | 86% | 65% | 1.32x | +20.7 | 2.03 |
| swept_swing_low_6m | true | 11 | 82% | 65% | 1.26x | +16.8 | 1.37 |
| swept_swing_low_3m | true | 24 | 79% | 65% | 1.22x | +14.1 | 1.54 |
| prior_vol_vs_med_quartile | Q4 | 36 | 78% | 65% | 1.20x | +12.7 | 1.59 |
| dist_sma6_atr_quartile | Q1 | 36 | 78% | 65% | 1.20x | +12.7 | 1.59 |
| dist_trail_atr_quartile | Q1 | 36 | 78% | 65% | 1.20x | +12.7 | 1.59 |
| prior_bear | true | 49 | 78% | 65% | 1.19x | +12.5 | 1.75 |
| prior_ma_reverted | true | 22 | 77% | 65% | 1.19x | +12.2 | 1.25 |
| prior_range_vs_med_quartile | Q4 | 36 | 75% | 65% | 1.15x | +10.0 | 1.21 |
| prior_atr_vs_mean_quartile | Q4 | 36 | 75% | 65% | 1.15x | +10.0 | 1.21 |

### US30

| Feature | Bucket | N | Hit% | Base% | Lift | Δpp | z |
|---|---|---:|---:|---:|---:|---:|---:|
| prior_bear | true | 29 | 79% | 61% | 1.30x | +18.3 | 1.98 |
| prior_engulf_bear | true | 9 | 78% | 61% | 1.28x | +16.8 | 1.13 |
| prior_weeks_toward_trail | true | 31 | 71% | 61% | 1.16x | +10.0 | 1.02 |

### YM

| Feature | Bucket | N | Hit% | Base% | Lift | Δpp | z |
|---|---|---:|---:|---:|---:|---:|---:|
| prior_engulf_bear | true | 8 | 88% | 60% | 1.47x | +27.8 | 2.24 |
| cal_month | 12 | 11 | 82% | 60% | 1.37x | +22.1 | 1.79 |
| month_name | Dec | 11 | 82% | 60% | 1.37x | +22.1 | 1.79 |
| prior_atr_wide | true | 10 | 80% | 60% | 1.34x | +20.3 | 1.53 |
| prior_vol_buildup | true | 22 | 77% | 60% | 1.29x | +17.6 | 1.79 |
| prior_atr_vs_mean_quartile | Q1 | 36 | 75% | 60% | 1.26x | +15.3 | 1.84 |
| prior_ma_reverted | true | 23 | 74% | 60% | 1.24x | +14.2 | 1.42 |
| quarter | 4 | 34 | 74% | 60% | 1.23x | +13.8 | 1.61 |
| orb_range_atr_quartile | Q4 | 36 | 72% | 60% | 1.21x | +12.5 | 1.47 |
| prior_weeks_toward_trail | true | 50 | 70% | 60% | 1.17x | +10.3 | 1.34 |
| prior_vol_vs_med_quartile | Q4 | 36 | 69% | 60% | 1.16x | +9.7 | 1.12 |
| dist_sma6_atr_quartile | Q1 | 36 | 69% | 60% | 1.16x | +9.7 | 1.12 |

## Protective / skip signals (lift≤0.85, true bucket)

### NQ

| Feature | N | Hit% | Lift | Δpp | z |
|---|---:|---:|---:|---:|---:|
| ext_above_sma6 | 36 | 50% | 0.77x | -15.0 | -1.63 |

### US30

| Feature | N | Hit% | Lift | Δpp | z |
|---|---:|---:|---:|---:|---:|
| prior_range_wide | 29 | 52% | 0.85x | -9.3 | -0.86 |
| prior_bull | 53 | 51% | 0.84x | -10.0 | -1.15 |
| swept_swing_low_3m | 15 | 40% | 0.66x | -21.0 | -1.53 |
| swept_swing_low_6m | 11 | 36% | 0.60x | -24.6 | -1.59 |
| ext_above_sma6 | 11 | 27% | 0.45x | -33.7 | -2.33 |

### YM

| Feature | N | Hit% | Lift | Δpp | z |
|---|---:|---:|---:|---:|---:|
| prior_weeks_away_trail | 46 | 50% | 0.84x | -9.7 | -1.15 |
| ext_above_sma6 | 22 | 45% | 0.76x | -14.3 | -1.25 |
| prior_doji | 15 | 40% | 0.67x | -19.7 | -1.48 |
| swept_swing_low_6m | 11 | 36% | 0.61x | -23.4 | -1.55 |
| swept_swing_low_12m | 8 | 25% | 0.42x | -34.7 | -2.19 |

## Forward weekly ATR-trail after touch months

| Touch label | Cohort | Outcome | N | Rate |
|---|---|---|---:|---:|
| touch_pct75_any | touch | fwd_weeks_toward_trail | 50 | 42% |
| touch_pct75_any | no_touch | fwd_weeks_toward_trail | 30 | 23% |
| touch_pct75_any | touch | fwd_weeks_away_trail | 50 | 42% |
| touch_pct75_any | no_touch | fwd_weeks_away_trail | 30 | 33% |
| touch_max_any | touch | fwd_weeks_toward_trail | 61 | 38% |
| touch_max_any | no_touch | fwd_weeks_toward_trail | 19 | 26% |
| touch_max_any | touch | fwd_weeks_away_trail | 61 | 39% |
| touch_max_any | no_touch | fwd_weeks_away_trail | 19 | 37% |
| touch_pct75_any | touch | fwd_weeks_toward_trail | 92 | 36% |
| touch_pct75_any | no_touch | fwd_weeks_toward_trail | 49 | 45% |
| touch_pct75_any | touch | fwd_weeks_away_trail | 92 | 45% |
| touch_pct75_any | no_touch | fwd_weeks_away_trail | 49 | 22% |
| touch_max_any | touch | fwd_weeks_toward_trail | 112 | 36% |
| touch_max_any | no_touch | fwd_weeks_toward_trail | 29 | 52% |
| touch_max_any | touch | fwd_weeks_away_trail | 112 | 39% |
| touch_max_any | no_touch | fwd_weeks_away_trail | 29 | 28% |
| touch_pct75_any | touch | fwd_weeks_toward_trail | 85 | 38% |
| touch_pct75_any | no_touch | fwd_weeks_toward_trail | 57 | 32% |
| touch_pct75_any | touch | fwd_weeks_away_trail | 85 | 39% |
| touch_pct75_any | no_touch | fwd_weeks_away_trail | 57 | 33% |
| touch_max_any | touch | fwd_weeks_toward_trail | 108 | 39% |
| touch_max_any | no_touch | fwd_weeks_toward_trail | 34 | 24% |
| touch_max_any | touch | fwd_weeks_away_trail | 108 | 38% |
| touch_max_any | no_touch | fwd_weeks_away_trail | 34 | 32% |

## Top pairwise combos (exploratory)

### NQ

| Combo | N | Hit% | Lift |
|---|---:|---:|---:|
| prior_vol_buildup AND prior_bear | 15 | 93% | 1.44x |
| prior_vol_buildup AND swept_swing_low_3m | 11 | 91% | 1.40x |
| prior_atr_reverted AND prior_bear | 10 | 90% | 1.38x |
| swept_swing_low_6m AND prior_bear | 8 | 88% | 1.35x |
| swept_swing_low_3m AND prior_bear | 15 | 87% | 1.33x |
| swept_swing_low_6m AND swept_swing_low_3m | 11 | 82% | 1.26x |
| prior_bear AND prior_ma_reverted | 15 | 80% | 1.23x |

### US30

| Combo | N | Hit% | Lift |
|---|---:|---:|---:|
| prior_bear AND prior_ma_reverted | 8 | 88% | 1.44x |
| prior_bear AND orb_wide | 13 | 85% | 1.39x |
| prior_bear AND prior_weeks_toward_trail | 19 | 84% | 1.38x |
| prior_bear AND prior_engulf_bear | 9 | 78% | 1.28x |
| prior_weeks_toward_trail AND orb_wide | 12 | 75% | 1.23x |
| prior_weeks_toward_trail AND prior_ma_reverted | 12 | 67% | 1.09x |

### YM

| Combo | N | Hit% | Lift |
|---|---:|---:|---:|
| prior_vol_buildup AND prior_weeks_toward_trail | 10 | 90% | 1.51x |
| prior_engulf_bear AND prior_bear | 8 | 88% | 1.47x |
| prior_weeks_toward_trail AND orb_wide | 18 | 83% | 1.40x |
| prior_vol_buildup AND prior_bear | 16 | 81% | 1.36x |
| prior_bear AND orb_wide | 20 | 80% | 1.34x |
| prior_ma_reverted AND prior_bear | 14 | 79% | 1.32x |
| prior_ma_reverted AND orb_wide | 9 | 78% | 1.30x |
| prior_weeks_toward_trail AND prior_bear | 27 | 74% | 1.24x |
| prior_ma_reverted AND prior_weeks_toward_trail | 18 | 72% | 1.21x |
| prior_vol_buildup AND orb_wide | 17 | 71% | 1.18x |

## Notes

- Band = causal rolling **6** prior months mean(min/med/max).
- Opening-week ORB is allowed (strategy already waits until after week 1).
- Swing sweeps / candle patterns / volume / ATR width use **prior completed** month only.
- Forward trail stats are consequences, not entry filters.
