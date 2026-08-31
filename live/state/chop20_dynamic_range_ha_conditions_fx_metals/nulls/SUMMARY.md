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
