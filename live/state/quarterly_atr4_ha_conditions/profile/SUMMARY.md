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
