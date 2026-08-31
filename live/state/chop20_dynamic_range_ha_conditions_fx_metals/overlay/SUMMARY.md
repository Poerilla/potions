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
