# Quarterly ATR4 fade ladder — HA mill

## Profile

# Quarterly ATR4 ladder — HA condition profile

High-probability condition study on **best be8 ladder books** (tp1–tp4 scale-out).
Features: same entry-asof mill as intraday HA (DOW / week-of-month / hour / 5m MA /
hourly RSI+OBV / ATR quartile / prior range-half). Diagnostic — not a promotion gate.

min_n=5 (lower than intraday because quarterly N is thin).

## Books

- **GBPUSD first_lower (be8 best-path)**: n=51 WR=51.0% avg=$7924 net=$404130  (first_lower / best_path)
- **NAS100 first_lower (be8 best-path)**: n=9 WR=33.3% avg=$3681 net=$33127  (first_lower / best_path)
- **XAUUSD first_only family (be8)**: n=30 WR=46.7% avg=$8368 net=$251054  (first_only_lower / family)
- **NQ second_after_upper (be8 best-path)**: n=8 WR=50.0% avg=$38370 net=$306962  (second_after_upper / best_path)
- **EURUSD second_after_upper (be8 best-path)**: n=16 WR=37.5% avg=$5289 net=$84627  (second_after_upper / best_path)

## Notables (positive WR + avg lift)

| book | condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| nq_second_after_upper | Prior-month range half | month_aligned | 5 | 80% | +30.0 | $62872 | $+24502 | 1.05 |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | 7 | 57% | +19.6 | $14129 | $+8840 | 0.90 |
| eurusd_second_after_upper | Day of week | Monday | 6 | 67% | +29.2 | $13007 | $+7718 | 1.26 |
| xauusd_first_only | Week of month | 2 | 13 | 62% | +14.9 | $15377 | $+7009 | 0.90 |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | 13 | 69% | +18.3 | $14615 | $+6690 | 1.18 |
| gbpusd_first_lower | Day of week | Monday | 15 | 60% | +9.0 | $13945 | $+6021 | 0.61 |
| xauusd_first_only | ATR14 quartile | atr_q4 | 8 | 50% | +3.3 | $14079 | $+5710 | 0.17 |
| gbpusd_first_lower | Entry hour (NY) | 12 | 9 | 56% | +4.6 | $13179 | $+5255 | 0.25 |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | 6 | 67% | +20.0 | $12573 | $+4205 | 0.90 |
| xauusd_first_only | ATR14 quartile | atr_q1 | 8 | 75% | +28.3 | $11650 | $+3281 | 1.43 |
| gbpusd_first_lower | Week of month | 3 | 6 | 67% | +15.7 | $11112 | $+3188 | 0.73 |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | 5 | 40% | +2.5 | $7714 | $+2425 | 0.10 |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_ha_conditions/profile`


## Overlay

# Quarterly ATR4 ladder — HA overlays

Filter / 1.25× / 1.5× on profile notables vs each book's baseline tape.

## Full-tape ranked by ΔN/S

| book | condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| nq_second_after_upper | Prior-month range half | month_aligned | filter | 62% | $+7399 | +593.32 | $314361 | 633.28 | live_ready |
| nq_second_after_upper | Prior-month range half | month_aligned | size_1.5 | 62% | $+157180 | +18.57 | $464142 | 58.54 | live_ready |
| nq_second_after_upper | Prior-month range half | month_aligned | size_1.25 | 62% | $+78590 | +9.43 | $385552 | 49.40 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | filter | 27% | $-157858 | +7.69 | $93197 | 13.18 | needs_rolling_proxy |
| xauusd_first_only | Week of month | 2 | filter | 43% | $-51150 | +7.21 | $199904 | 12.70 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | filter | 38% | $-6582 | +5.68 | $78045 | 9.54 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | filter | 44% | $+14276 | +5.47 | $98902 | 9.32 | live_ready |
| gbpusd_first_lower | Entry hour (NY) | 12 | filter | 18% | $-285522 | +2.98 | $118608 | 16.20 | live_ready |
| gbpusd_first_lower | Day of week | Monday | filter | 29% | $-194957 | +2.86 | $209173 | 16.08 | live_ready |
| gbpusd_first_lower | Entry hour (NY) | 12 | size_1.5 | 18% | $+59304 | +1.94 | $463435 | 15.16 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | size_1.5 | 44% | $+49451 | +1.83 | $134078 | 5.68 | live_ready |
| gbpusd_first_lower | Day of week | Monday | size_1.5 | 29% | $+104587 | +1.77 | $508717 | 14.99 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | size_1.5 | 38% | $+39022 | +1.48 | $123649 | 5.34 | live_ready |
| xauusd_first_only | Week of month | 2 | size_1.5 | 43% | $+99952 | +1.35 | $351007 | 6.84 | live_ready |
| gbpusd_first_lower | Week of month | 3 | size_1.5 | 12% | $+33337 | +1.09 | $437467 | 14.31 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | size_1.5 | 27% | $+46598 | +1.02 | $297653 | 6.51 | needs_rolling_proxy |
| gbpusd_first_lower | Entry hour (NY) | 12 | size_1.25 | 18% | $+29652 | +0.97 | $433782 | 14.19 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | size_1.25 | 44% | $+24726 | +0.95 | $109352 | 4.80 | live_ready |
| gbpusd_first_lower | Day of week | Monday | size_1.25 | 29% | $+52293 | +0.93 | $456424 | 14.15 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | size_1.25 | 38% | $+19511 | +0.76 | $104138 | 4.62 | live_ready |
| xauusd_first_only | Week of month | 2 | size_1.25 | 43% | $+49976 | +0.71 | $301031 | 6.20 | live_ready |
| gbpusd_first_lower | Week of month | 3 | size_1.25 | 12% | $+16669 | +0.55 | $420799 | 13.77 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | size_1.25 | 27% | $+23299 | +0.51 | $274354 | 6.00 | needs_rolling_proxy |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | size_1.5 | 31% | $+19285 | +0.30 | $103912 | 4.16 | live_ready |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | size_1.25 | 31% | $+9643 | +0.16 | $94269 | 4.02 | live_ready |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | filter | 31% | $-46056 | +0.10 | $38571 | 3.96 | live_ready |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | size_1.25 | 20% | $+18860 | -0.24 | $269914 | 5.25 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q4 | size_1.25 | 27% | $+28157 | -0.35 | $279212 | 5.14 | needs_rolling_proxy |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | size_1.5 | 20% | $+37719 | -0.43 | $288774 | 5.06 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q4 | size_1.5 | 27% | $+56314 | -0.60 | $307369 | 4.89 | needs_rolling_proxy |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | size_1.25 | 25% | $+47497 | -1.40 | $451628 | 11.82 | needs_rolling_proxy |
| xauusd_first_only | ATR14 quartile | atr_q4 | filter | 27% | $-138426 | -2.20 | $112628 | 3.29 | needs_rolling_proxy |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | size_1.5 | 25% | $+94995 | -2.34 | $499125 | 10.89 | needs_rolling_proxy |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | filter | 20% | $-175616 | -3.22 | $75438 | 2.27 | live_ready |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | filter | 25% | $-214141 | -7.01 | $189989 | 6.22 | needs_rolling_proxy |
| gbpusd_first_lower | Week of month | 3 | filter | 12% | $-337456 | -7.33 | $66674 | 5.89 | live_ready |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_ha_conditions/overlay`


## Nulls

# Quarterly ATR4 ladder — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay.
Quarterly N is thin — treat VALIDATED claims cautiously.

| decision | book | condition=bucket | hp% | ΔN/S | Δnet | p_plac | p_shift | p_master |
|---|---|---|---:|---:|---:|---:|---:|---:|
| NOT VALIDATED | gbpusd_first_lower | Entry hour (NY)=12 | 18% | +0.97 | $+29652 | 1.000 | 0.908 | 0.569 |
| NOT VALIDATED | gbpusd_first_lower | Day of week=Monday | 29% | +0.93 | $+52293 | 1.000 | 0.951 | 0.539 |
| NOT VALIDATED | gbpusd_first_lower | Week of month=3 | 12% | +0.55 | $+16669 | 1.000 | 0.925 | 0.656 |
| NOT VALIDATED | eurusd_second_after_upper | Hourly RSI bucket=rsi_30_45 | 31% | +0.16 | $+9643 | 1.000 | 0.936 | nan |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_ha_conditions/nulls`

