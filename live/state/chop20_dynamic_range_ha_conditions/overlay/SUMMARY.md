# CHOP20 boundary60 — HA overlay

Filter / 1.25× / 1.5× on notable buckets. Thin-N book — diagnostic only.

| book | condition=bucket | policy | ΔN/S | Δnet | hp% | causal |
|---|---|---|---:|---:|---:|---|
| nq_chop20_boundary60_1m | Hourly RSI bucket=rsi_gt70 | filter | +42.09 | $-108982 | 20% | live_ready |
| nq_chop20_boundary60_1m | Hourly RSI vs trade=rsi_with_side | filter | +16.05 | $+28015 | 78% | live_ready |
| mnq_chop20_boundary60_1m | Week of month=3 | filter | +16.00 | $+106 | 29% | live_ready |
| nq_chop20_boundary60_1m | Week of month=3 | filter | +13.59 | $-203125 | 28% | live_ready |
| ym_chop20_boundary60_1m | Prior-week range half=week_aligned | filter | +6.22 | $+58232 | 18% | live_ready |
| nq_chop20_boundary60_1m | Day of week=Monday | filter | +5.99 | $-210151 | 25% | live_ready |
| nq_chop20_boundary60_1m | Hourly RSI bucket=rsi_gt70 | size_1.5 | +4.32 | $+180552 | 20% | live_ready |
| nq_chop20_boundary60_1m | Hourly RSI vs trade=rsi_with_side | size_1.5 | +3.39 | $+249051 | 78% | live_ready |
| ym_chop20_boundary60_1m | Hourly RSI bucket=rsi_55_70 | filter | +3.26 | $+107547 | 33% | live_ready |
| ym_chop20_boundary60_1m | Hourly OBV vs trade=obv_opposed | filter | +3.01 | $+66215 | 18% | live_ready |
| nq_chop20_boundary60_1m | Week of month=3 | size_1.5 | +2.77 | $+133481 | 28% | live_ready |
| mnq_chop20_boundary60_1m | Week of month=3 | size_1.5 | +2.53 | $+11606 | 29% | live_ready |
| nq_chop20_boundary60_1m | Hourly RSI bucket=rsi_gt70 | size_1.25 | +2.16 | $+90276 | 20% | live_ready |
| ym_chop20_boundary60_1m | 5m MA vs trade=ma_opposed | filter | +2.13 | $+70296 | 37% | live_ready |
| nq_chop20_boundary60_1m | Hourly RSI vs trade=rsi_with_side | size_1.25 | +1.83 | $+124526 | 78% | live_ready |
| nq_chop20_boundary60_1m | Week of month=3 | size_1.25 | +1.60 | $+66740 | 28% | live_ready |
| mnq_chop20_boundary60_1m | Week of month=3 | size_1.25 | +1.38 | $+5803 | 29% | live_ready |
| nq_chop20_boundary60_1m | Day of week=Thursday | size_1.5 | +1.22 | $+50754 | 13% | live_ready |
| nq_chop20_boundary60_1m | Day of week=Monday | size_1.5 | +0.92 | $+129968 | 25% | live_ready |
| nq_chop20_boundary60_1m | Day of week=Thursday | size_1.25 | +0.61 | $+25377 | 13% | live_ready |
| nq_chop20_boundary60_1m | Day of week=Monday | size_1.25 | +0.50 | $+64984 | 25% | live_ready |
| ym_chop20_boundary60_1m | Hourly RSI bucket=rsi_55_70 | size_1.5 | +0.48 | $+50667 | 33% | live_ready |
| ym_chop20_boundary60_1m | Hourly OBV vs trade=obv_opposed | size_1.5 | +0.30 | $+30001 | 18% | live_ready |
| ym_chop20_boundary60_1m | 5m MA vs trade=ma_opposed | size_1.5 | +0.26 | $+32042 | 37% | live_ready |
| ym_chop20_boundary60_1m | Hourly RSI bucket=rsi_55_70 | size_1.25 | +0.23 | $+25333 | 33% | live_ready |
| ym_chop20_boundary60_1m | Prior-week range half=week_aligned | size_1.5 | +0.23 | $+26010 | 18% | live_ready |
| ym_chop20_boundary60_1m | Hourly OBV vs trade=obv_opposed | size_1.25 | +0.14 | $+15000 | 18% | live_ready |
| ym_chop20_boundary60_1m | 5m MA vs trade=ma_opposed | size_1.25 | +0.14 | $+16021 | 37% | live_ready |
| ym_chop20_boundary60_1m | Prior-week range half=week_aligned | size_1.25 | +0.12 | $+13005 | 18% | live_ready |
| nq_chop20_boundary60_1m | Week of month=1 | size_1.5 | +0.10 | $+80910 | 22% | live_ready |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions/overlay`
