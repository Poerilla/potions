# Monthly ATR pct75 lookback — skip / size overlay

Wired lookback predictors onto the **pct75 / rolling-6m** pandas fade book.
Gate = **Δnet + ΔN/S** on chronological OOS (last 40%), not touch-rate lift.

## Baselines (full tape)

| Market | N | Net $ | Stress $ | N/S | WR |
|---|---:|---:|---:|---:|---:|
| NQ | 102 | 344,824 | 240,071 | 1.44 | 26% |
| US30 | 54 | -3,935 | 37,150 | -0.11 | 30% |
| YM | 93 | -12,513 | 129,950 | -0.10 | 32% |
| PORT | 249 | 328,375 | 375,977 | 0.87 | 29% |

## Candidates from lookback lift

| Kind | Market | Feature | Bucket | Lift n | Lift | z |
|---|---|---|---|---:|---:|---:|
| hp | NQ | prior_vol_buildup | true | 20 | 1.46x | 4.76 |
| hp | NQ | prior_atr_reverted | true | 16 | 1.44x | 3.96 |
| hp | NQ | cal_month | 7 | 10 | 1.38x | 2.43 |
| hp | NQ | month_name | Jul | 10 | 1.38x | 2.43 |
| hp | NQ | prior_atr_wide | true | 14 | 1.32x | 2.03 |
| hp | NQ | swept_swing_low_6m | true | 11 | 1.26x | 1.37 |
| hp | NQ | swept_swing_low_3m | true | 24 | 1.22x | 1.54 |
| hp | US30 | prior_bear | true | 29 | 1.30x | 1.98 |
| hp | YM | prior_engulf_bear | true | 8 | 1.47x | 2.24 |
| hp | YM | cal_month | 12 | 11 | 1.37x | 1.79 |
| hp | YM | month_name | Dec | 11 | 1.37x | 1.79 |
| hp | YM | prior_atr_wide | true | 10 | 1.34x | 1.53 |
| hp | YM | prior_vol_buildup | true | 22 | 1.29x | 1.79 |
| hp | YM | prior_ma_reverted | true | 23 | 1.24x | 1.42 |
| hp | YM | quarter | 4 | 34 | 1.23x | 1.61 |
| skip | NQ | ext_above_sma6 | true | 36 | 0.77x | -1.63 |
| skip | US30 | prior_range_wide | true | 29 | 0.85x | -0.86 |
| skip | US30 | prior_bull | true | 53 | 0.84x | -1.15 |
| skip | US30 | swept_swing_low_3m | true | 15 | 0.66x | -1.53 |
| skip | US30 | swept_swing_low_6m | true | 11 | 0.60x | -1.59 |
| skip | US30 | ext_above_sma6 | true | 11 | 0.45x | -2.33 |
| skip | YM | prior_weeks_away_trail | true | 46 | 0.84x | -1.15 |
| skip | YM | ext_above_sma6 | true | 22 | 0.76x | -1.25 |
| skip | YM | prior_doji | true | 15 | 0.67x | -1.48 |
| skip | YM | swept_swing_low_6m | true | 11 | 0.61x | -1.55 |
| skip | YM | swept_swing_low_12m | true | 8 | 0.42x | -2.19 |

## OOS overlay scorecard (Δnet / ΔN/S)

| Stance | Market | Feature | Policy | Hit n | Net $ | Δnet | N/S | ΔN/S | Stress |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| reject_filter | NQ | prior_atr_reverted=true | filter | 8 | 289,628 | -111,527 | 5.79 | +4.10 | 50,014 |
| thin | YM | prior_engulf_bear=true | filter | 4 | 30,748 | +84,218 | 2.12 | +2.92 | 14,536 |
| retain_filter | YM | quarter=4 | filter | 11 | 5,661 | +59,131 | 0.10 | +0.91 | 58,790 |
| thin | NQ | swept_swing_low_6m=true | filter | 5 | 128,512 | -272,643 | 2.57 | +0.88 | 50,014 |
| worth_size | NQ | prior_atr_reverted=true | size_1.5 | 8 | 545,969 | +144,814 | 2.13 | +0.44 | 256,199 |
| thin | YM | prior_vol_buildup=true | filter | 3 | -8,456 | +45,014 | -0.51 | +0.30 | 16,466 |
| retain_size | YM | prior_engulf_bear=true | size_1.5 | 4 | -38,096 | +15,374 | -0.58 | +0.23 | 66,058 |
| worth_size | NQ | prior_atr_reverted=true | size_1.25 | 8 | 473,562 | +72,407 | 1.92 | +0.23 | 246,703 |
| worth_size | US30 | prior_bear=true | size_1.5 | 9 | 22,402 | +4,916 | 1.97 | +0.22 | 11,398 |
| retain_size | YM | quarter=4 | size_1.5 | 11 | -50,639 | +2,830 | -0.65 | +0.16 | 78,075 |
| retain_size | NQ | cal_month=7 | size_1.5 | 4 | 426,856 | +25,701 | 1.83 | +0.14 | 233,721 |
| retain_size | NQ | month_name=Jul | size_1.5 | 4 | 426,856 | +25,701 | 1.83 | +0.14 | 233,721 |
| worth_size | US30 | prior_bear=true | size_1.25 | 9 | 19,944 | +2,458 | 1.86 | +0.12 | 10,716 |
| retain_size | YM | prior_engulf_bear=true | size_1.25 | 4 | -45,783 | +7,687 | -0.69 | +0.12 | 66,058 |
| retain_size | NQ | cal_month=7 | size_1.25 | 4 | 414,006 | +12,851 | 1.78 | +0.09 | 232,817 |
| retain_size | NQ | month_name=Jul | size_1.25 | 4 | 414,006 | +12,851 | 1.78 | +0.09 | 232,817 |
| worth_size | NQ | swept_swing_low_6m=true | size_1.5 | 5 | 465,411 | +64,256 | 1.75 | +0.06 | 265,912 |
| retain_size | YM | quarter=4 | size_1.25 | 11 | -52,055 | +1,415 | -0.75 | +0.05 | 68,947 |
| reject_size | YM | prior_vol_buildup=true | size_1.5 | 3 | -57,698 | -4,228 | -0.78 | +0.03 | 74,291 |
| worth_size | NQ | swept_swing_low_6m=true | size_1.25 | 5 | 433,283 | +32,128 | 1.72 | +0.03 | 251,559 |
| reject_size | YM | prior_vol_buildup=true | size_1.25 | 3 | -55,584 | -2,114 | -0.79 | +0.02 | 70,175 |
| thin | YM | prior_atr_wide=true | filter | 3 | -38,848 | +14,622 | -0.84 | -0.03 | 46,315 |
| reject_size | YM | prior_atr_wide=true | size_1.5 | 3 | -72,894 | -19,424 | -0.85 | -0.04 | 86,079 |
| reject_size | YM | prior_atr_wide=true | size_1.25 | 3 | -63,182 | -9,712 | -0.85 | -0.04 | 74,500 |
| reject_size | NQ | prior_vol_buildup=true | size_1.25 | 3 | 390,174 | -10,981 | 1.64 | -0.05 | 237,207 |
| retain_size | NQ | swept_swing_low_3m=true | size_1.25 | 9 | 421,255 | +20,100 | 1.62 | -0.07 | 259,362 |
| reject_size | YM | prior_ma_reverted=true | size_1.25 | 6 | -69,834 | -16,364 | -0.88 | -0.07 | 79,167 |
| reject_size | YM | prior_ma_reverted=true | size_1.5 | 6 | -86,198 | -32,728 | -0.89 | -0.08 | 97,398 |
| reject_size | YM | cal_month=12 | size_1.25 | 3 | -63,460 | -9,990 | -0.89 | -0.09 | 70,926 |
| reject_size | YM | month_name=Dec | size_1.25 | 3 | -63,460 | -9,990 | -0.89 | -0.09 | 70,926 |
| thin | YM | prior_ma_reverted=true | filter | 6 | -65,456 | -11,987 | -0.90 | -0.09 | 72,923 |
| reject_size | NQ | prior_vol_buildup=true | size_1.5 | 3 | 379,194 | -21,961 | 1.60 | -0.09 | 237,207 |
| reject_size | YM | cal_month=12 | size_1.5 | 3 | -73,449 | -19,980 | -0.91 | -0.10 | 80,916 |
| reject_size | YM | month_name=Dec | size_1.5 | 3 | -73,449 | -19,980 | -0.91 | -0.10 | 80,916 |
| retain_size | NQ | swept_swing_low_3m=true | size_1.5 | 9 | 441,354 | +40,199 | 1.57 | -0.12 | 281,516 |
| reject_size | NQ | prior_atr_wide=true | size_1.25 | 3 | 381,098 | -20,057 | 1.56 | -0.13 | 244,307 |
| reject_size | NQ | prior_atr_wide=true | size_1.5 | 3 | 361,040 | -40,114 | 1.44 | -0.26 | 251,407 |
| thin | NQ | cal_month=7 | filter | 4 | 51,403 | -349,752 | 1.25 | -0.44 | 41,247 |
| thin | NQ | month_name=Jul | filter | 4 | 51,403 | -349,752 | 1.25 | -0.44 | 41,247 |
| thin | YM | cal_month=12 | filter | 3 | -39,959 | +13,510 | -1.29 | -0.48 | 31,068 |
| thin | YM | month_name=Dec | filter | 3 | -39,959 | +13,510 | -1.29 | -0.48 | 31,068 |
| reject_filter | US30 | prior_bear=true | filter | 9 | 9,833 | -7,653 | 1.01 | -0.73 | 9,726 |
| reject_filter | NQ | swept_swing_low_3m=true | filter | 9 | 80,399 | -320,756 | 0.94 | -0.75 | 85,366 |
| thin | NQ | prior_vol_buildup=true | filter | 3 | -43,922 | -445,077 | -0.88 | -2.57 | 50,014 |
| thin | NQ | prior_atr_wide=true | filter | 3 | -80,229 | -481,384 | -1.18 | -2.87 | 67,874 |
| thin | US30 | ext_above_sma6=true | skip | 2 | 20,325 | +2,839 | 2.83 | +1.08 | 7,194 |
| reject_skip | US30 | prior_range_wide=true | skip | 5 | 14,788 | -2,698 | 2.11 | +0.37 | 6,997 |
| retain_skip | YM | prior_weeks_away_trail=true | skip | 13 | -40,342 | +13,128 | -0.52 | +0.29 | 77,407 |
| thin | YM | swept_swing_low_12m=true | skip | 1 | -39,902 | +13,567 | -0.60 | +0.21 | 66,058 |
| thin | YM | swept_swing_low_6m=true | skip | 3 | -47,912 | +5,557 | -0.73 | +0.08 | 66,058 |
| thin | YM | prior_doji=true | skip | 0 | -53,470 | +0 | -0.81 | +0.00 | 66,058 |
| thin | YM | ext_above_sma6=true | skip | 3 | -78,824 | -25,354 | -0.91 | -0.10 | 86,290 |
| reject_skip | NQ | ext_above_sma6=true | skip | 9 | 341,540 | -59,614 | 1.38 | -0.32 | 248,351 |
| thin | US30 | swept_swing_low_3m=true | skip | 1 | 12,033 | -5,453 | 1.20 | -0.54 | 10,033 |
| thin | US30 | swept_swing_low_6m=true | skip | 1 | 12,033 | -5,453 | 1.20 | -0.54 | 10,033 |
| reject_skip | US30 | prior_bull=true | skip | 13 | 9,833 | -7,653 | 1.01 | -0.73 | 9,726 |

## Stance

- **Do not promote** from lookback lift alone.
- **worth_*** = OOS net/N/S cleared heuristic; still needs nulls before paper.
- **retain_*** = mixed; shadow only.
- **reject_*** / **thin** = no action.

Cleared `worth_*` this run:
- NQ hp prior_atr_reverted=true size_1.25: Δnet=+72,407 ΔN/S=+0.23
- NQ hp prior_atr_reverted=true size_1.5: Δnet=+144,814 ΔN/S=+0.44
- NQ hp swept_swing_low_6m=true size_1.25: Δnet=+32,128 ΔN/S=+0.03
- NQ hp swept_swing_low_6m=true size_1.5: Δnet=+64,256 ΔN/S=+0.06
- US30 hp prior_bear=true size_1.25: Δnet=+2,458 ΔN/S=+0.12
- US30 hp prior_bear=true size_1.5: Δnet=+4,916 ΔN/S=+0.22
