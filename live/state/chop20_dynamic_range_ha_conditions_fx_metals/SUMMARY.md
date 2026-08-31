# CHOP20 Causal FX/metals — HA mill

Source: close_to_globex baselines under `/home/tester/hsm/potions/live/state/chop20_dynamic_range_causal_entry_fx_metals`.

## Profile

# CHOP20 boundary60 — HA condition profile

Diagnostic HP conditions on 1m path-aware campaign tapes.
min_n=6.

## Baselines

- **nas100_chop20_causal_globex**: n=74 WR=27% net=$15460 N/S=3.90
- **usdjpy_chop20_causal_globex**: n=168 WR=27% net=$6081394 N/S=1.60
- **xauusd_chop20_causal_globex**: n=128 WR=30% net=$348849 N/S=4.59

## Notables (top 40)

| book | condition | bucket | n | WR | WRΔpp | avgΔ |
|---|---|---|---:|---:|---:|---:|
| usdjpy_chop20_causal_globex | Hourly RSI bucket | rsi_45_55 | 41 | 37% | +9.8 | $+175555 |
| usdjpy_chop20_causal_globex | Hourly RSI vs trade | rsi_neutral | 41 | 37% | +9.8 | $+175555 |
| usdjpy_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 19 | 37% | +10.1 | $+87505 |
| usdjpy_chop20_causal_globex | Entry hour (NY) | 22 | 7 | 29% | +1.8 | $+77832 |
| usdjpy_chop20_causal_globex | Week of month | 2 | 36 | 36% | +9.3 | $+67656 |
| usdjpy_chop20_causal_globex | ATR14 quartile | atr_q4 | 42 | 29% | +1.8 | $+63985 |
| usdjpy_chop20_causal_globex | Hourly OBV vs trade | obv_opposed | 59 | 31% | +3.7 | $+56730 |
| usdjpy_chop20_causal_globex | Day of week | Friday | 34 | 35% | +8.5 | $+55544 |
| usdjpy_chop20_causal_globex | Prior-week range half | week_aligned | 36 | 33% | +6.5 | $+40869 |
| usdjpy_chop20_causal_globex | Day of week | Sunday | 35 | 34% | +7.5 | $+32245 |
| usdjpy_chop20_causal_globex | 5m MA vs trade | ma_opposed | 80 | 30% | +3.2 | $+25112 |
| usdjpy_chop20_causal_globex | Entry hour (NY) | 21 | 28 | 36% | +8.9 | $+20849 |
| xauusd_chop20_causal_globex | Hourly RSI vs trade | rsi_against_side | 8 | 62% | +32.0 | $+9133 |
| xauusd_chop20_causal_globex | Prior-day range half | day_aligned | 21 | 48% | +17.2 | $+4535 |
| xauusd_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 14 | 36% | +5.2 | $+2478 |
| xauusd_chop20_causal_globex | ATR14 quartile | atr_q3 | 32 | 34% | +3.9 | $+2344 |
| xauusd_chop20_causal_globex | 5m MA cross vs trade | cross_opposed | 6 | 50% | +19.5 | $+1890 |
| xauusd_chop20_causal_globex | Week of month | 1 | 32 | 34% | +3.9 | $+1597 |
| xauusd_chop20_causal_globex | 5m MA vs trade | ma_aligned | 60 | 37% | +6.2 | $+1237 |
| xauusd_chop20_causal_globex | Week of month | 2 | 31 | 42% | +11.5 | $+1025 |
| nas100_chop20_causal_globex | Day of week | Wednesday | 11 | 36% | +9.3 | $+399 |
| nas100_chop20_causal_globex | Week of month | 3 | 14 | 43% | +15.8 | $+311 |
| nas100_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 12 | 42% | +14.6 | $+298 |
| nas100_chop20_causal_globex | ATR14 quartile | atr_q4 | 19 | 42% | +15.1 | $+290 |
| nas100_chop20_causal_globex | Day of week | Thursday | 16 | 31% | +4.2 | $+181 |
| nas100_chop20_causal_globex | 5m MA vs trade | ma_aligned | 39 | 28% | +1.2 | $+128 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions_fx_metals/profile`


## Overlay

# CHOP20 boundary60 — HA overlay

Filter / 1.25× / 1.5× on notable buckets. Thin-N book — diagnostic only.

| book | condition=bucket | policy | ΔN/S | Δnet | hp% | causal |
|---|---|---|---:|---:|---:|---|
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_45_55 | filter | +12.51 | $+2600522 | 24% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI vs trade=rsi_neutral | filter | +12.51 | $+2600522 | 24% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_gt70 | filter | +5.83 | $-3731029 | 11% | live_ready |
| usdjpy_chop20_causal_globex | Week of month=2 | filter | +2.98 | $-2342606 | 21% | live_ready |
| usdjpy_chop20_causal_globex | Prior-week range half=week_aligned | filter | +2.25 | $-3306956 | 21% | live_ready |
| usdjpy_chop20_causal_globex | Hourly OBV vs trade=obv_opposed | filter | +1.85 | $-598609 | 35% | live_ready |
| usdjpy_chop20_causal_globex | Day of week=Friday | filter | +1.73 | $-2962147 | 20% | live_ready |
| usdjpy_chop20_causal_globex | 5m MA vs trade=ma_opposed | filter | +1.25 | $-1176504 | 48% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_45_55 | size_1.5 | +0.95 | $+4340958 | 24% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI vs trade=rsi_neutral | size_1.5 | +0.95 | $+4340958 | 24% | live_ready |
| usdjpy_chop20_causal_globex | Entry hour (NY)=22 | filter | +0.50 | $-5283175 | 4% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_45_55 | size_1.25 | +0.49 | $+2170479 | 24% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI vs trade=rsi_neutral | size_1.25 | +0.49 | $+2170479 | 24% | live_ready |
| usdjpy_chop20_causal_globex | ATR14 quartile=atr_q4 | size_1.5 | +0.48 | $+2103855 | 25% | needs_rolling_proxy |
| usdjpy_chop20_causal_globex | Prior-week range half=week_aligned | size_1.5 | +0.44 | $+1387219 | 21% | live_ready |
| usdjpy_chop20_causal_globex | Day of week=Friday | size_1.5 | +0.40 | $+1559623 | 20% | live_ready |
| usdjpy_chop20_causal_globex | Hourly OBV vs trade=obv_opposed | size_1.5 | +0.35 | $+2741392 | 35% | live_ready |
| usdjpy_chop20_causal_globex | Week of month=2 | size_1.5 | +0.32 | $+1869394 | 21% | live_ready |
| usdjpy_chop20_causal_globex | ATR14 quartile=atr_q4 | filter | +0.29 | $-1873683 | 25% | needs_rolling_proxy |
| usdjpy_chop20_causal_globex | 5m MA vs trade=ma_opposed | size_1.5 | +0.28 | $+2452445 | 48% | live_ready |
| usdjpy_chop20_causal_globex | ATR14 quartile=atr_q4 | size_1.25 | +0.24 | $+1051928 | 25% | needs_rolling_proxy |
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_gt70 | size_1.5 | +0.23 | $+1175182 | 11% | live_ready |
| usdjpy_chop20_causal_globex | Prior-week range half=week_aligned | size_1.25 | +0.21 | $+693609 | 21% | live_ready |
| usdjpy_chop20_causal_globex | Day of week=Friday | size_1.25 | +0.20 | $+779812 | 20% | live_ready |
| usdjpy_chop20_causal_globex | Hourly OBV vs trade=obv_opposed | size_1.25 | +0.19 | $+1370696 | 35% | live_ready |
| usdjpy_chop20_causal_globex | Week of month=2 | size_1.25 | +0.17 | $+934697 | 21% | live_ready |
| usdjpy_chop20_causal_globex | 5m MA vs trade=ma_opposed | size_1.25 | +0.15 | $+1226222 | 48% | live_ready |
| usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_gt70 | size_1.25 | +0.12 | $+587591 | 11% | live_ready |
| usdjpy_chop20_causal_globex | Entry hour (NY)=22 | size_1.5 | +0.03 | $+399109 | 4% | live_ready |
| usdjpy_chop20_causal_globex | Entry hour (NY)=22 | size_1.25 | +0.02 | $+199555 | 4% | live_ready |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions_fx_metals/overlay`


## Nulls

# CHOP20 boundary60 — HA matched nulls

1.25× matched-added-exposure. Thin campaign N — treat VALIDATED cautiously.

| decision | book | condition=bucket | ΔN/S | p_master |
|---|---|---|---:|---:|
| NOT VALIDATED | usdjpy_chop20_causal_globex | Hourly RSI bucket=rsi_45_55 | +0.49 | 0.050 |
| NOT VALIDATED | usdjpy_chop20_causal_globex | Hourly RSI vs trade=rsi_neutral | +0.49 | 0.070 |
| NOT VALIDATED | usdjpy_chop20_causal_globex | ATR14 quartile=atr_q4 | +0.24 | 0.756 |
| RISK THROTTLE | usdjpy_chop20_causal_globex | Prior-week range half=week_aligned | +0.21 | 0.853 |
| NOT VALIDATED | usdjpy_chop20_causal_globex | Day of week=Friday | +0.20 | 0.853 |
| NOT VALIDATED | usdjpy_chop20_causal_globex | Hourly OBV vs trade=obv_opposed | +0.19 | 0.880 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions_fx_metals/nulls`


**Stance:** diagnostic HA — filter candidates only; re-sim on causal 1m before promote.

DSR: `TRL-2026-00183`

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions_fx_metals`
