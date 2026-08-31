# CHOP20 Dynamic Range — HA mill

Source structure: touch_broken_boundary + max_age_60 + 0.5/1/4R (1m path).

## Profile

# CHOP20 boundary60 — HA condition profile

Diagnostic HP conditions on 1m path-aware campaign tapes.
min_n=8.

## Baselines

- **nq_chop20_boundary60_1m**: n=69 WR=38% net=$470087 N/S=11.26
- **ym_chop20_boundary60_1m**: n=98 WR=28% net=$-6214 N/S=-0.06
- **mym_chop20_boundary60_1m**: n=48 WR=17% net=$-2981 N/S=-0.29
- **mnq_chop20_boundary60_1m**: n=31 WR=42% net=$23106 N/S=5.50

## Notables (top 40)

| book | condition | bucket | n | WR | WRΔpp | avgΔ |
|---|---|---|---:|---:|---:|---:|
| nq_chop20_boundary60_1m | Hourly RSI bucket | rsi_gt70 | 14 | 64% | +26.6 | $+18980 |
| nq_chop20_boundary60_1m | ATR14 quartile | atr_q4 | 17 | 53% | +15.3 | $+12804 |
| nq_chop20_boundary60_1m | Day of week | Monday | 17 | 47% | +9.4 | $+8477 |
| nq_chop20_boundary60_1m | Week of month | 3 | 19 | 42% | +4.4 | $+7238 |
| nq_chop20_boundary60_1m | Day of week | Thursday | 9 | 56% | +17.9 | $+4466 |
| nq_chop20_boundary60_1m | Week of month | 1 | 15 | 53% | +15.7 | $+3975 |
| ym_chop20_boundary60_1m | Hourly OBV vs trade | obv_opposed | 18 | 28% | +0.2 | $+3397 |
| ym_chop20_boundary60_1m | Hourly RSI bucket | rsi_55_70 | 32 | 31% | +3.7 | $+3230 |
| ym_chop20_boundary60_1m | Prior-week range half | week_aligned | 18 | 39% | +11.3 | $+2953 |
| nq_chop20_boundary60_1m | Hourly RSI vs trade | rsi_with_side | 54 | 43% | +4.9 | $+2411 |
| ym_chop20_boundary60_1m | 5m MA vs trade | ma_opposed | 36 | 42% | +14.1 | $+1843 |
| mnq_chop20_boundary60_1m | Week of month | 3 | 9 | 56% | +13.6 | $+1834 |
| ym_chop20_boundary60_1m | Week of month | 1 | 22 | 41% | +13.4 | $+1545 |
| ym_chop20_boundary60_1m | Prior-day range half | day_opposed | 85 | 28% | +0.7 | $+1210 |
| ym_chop20_boundary60_1m | ATR14 quartile | atr_q1 | 25 | 36% | +8.4 | $+928 |
| ym_chop20_boundary60_1m | Week of month | 4 | 14 | 36% | +8.2 | $+902 |
| ym_chop20_boundary60_1m | Day of week | Monday | 17 | 29% | +1.9 | $+753 |
| ym_chop20_boundary60_1m | ATR14 quartile | atr_q4 | 25 | 28% | +0.4 | $+712 |
| mym_chop20_boundary60_1m | ATR14 quartile | atr_q3 | 12 | 25% | +8.3 | $+692 |
| mym_chop20_boundary60_1m | Hourly OBV vs trade | obv_opposed | 12 | 25% | +8.3 | $+577 |
| mym_chop20_boundary60_1m | Week of month | 1 | 10 | 40% | +23.3 | $+518 |
| mym_chop20_boundary60_1m | Week of month | 5 | 8 | 25% | +8.3 | $+514 |
| mnq_chop20_boundary60_1m | Hourly RSI vs trade | rsi_with_side | 22 | 50% | +8.1 | $+471 |
| mnq_chop20_boundary60_1m | Day of week | Monday | 9 | 56% | +13.6 | $+413 |
| mnq_chop20_boundary60_1m | Hourly OBV vs trade | obv_aligned | 21 | 48% | +5.7 | $+412 |
| ym_chop20_boundary60_1m | Day of week | Tuesday | 19 | 32% | +4.0 | $+403 |
| ym_chop20_boundary60_1m | Hourly RSI vs trade | rsi_with_side | 81 | 31% | +3.3 | $+401 |
| mym_chop20_boundary60_1m | Day of week | Friday | 11 | 18% | +1.5 | $+372 |
| ym_chop20_boundary60_1m | Day of week | Thursday | 20 | 30% | +2.4 | $+194 |
| ym_chop20_boundary60_1m | 5m MA cross vs trade | cross_none | 89 | 29% | +1.7 | $+180 |
| mym_chop20_boundary60_1m | 5m MA vs trade | ma_aligned | 34 | 21% | +3.9 | $+35 |
| mym_chop20_boundary60_1m | Prior-month range half | month_opposed | 43 | 19% | +1.9 | $+28 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions/profile`


## Overlay

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


## Nulls

# CHOP20 boundary60 — HA matched nulls

1.25× matched-added-exposure. Thin campaign N — treat VALIDATED cautiously.

| decision | book | condition=bucket | ΔN/S | p_master |
|---|---|---|---:|---:|
| NOT VALIDATED | nq_chop20_boundary60_1m | Hourly RSI bucket=rsi_gt70 | +2.16 | 0.204 |
| RISK THROTTLE | nq_chop20_boundary60_1m | Week of month=3 | +1.60 | 0.549 |
| NOT VALIDATED | mnq_chop20_boundary60_1m | Week of month=3 | +1.38 | 0.040 |
| NOT VALIDATED | nq_chop20_boundary60_1m | Day of week=Thursday | +0.61 | 0.968 |
| NOT VALIDATED | nq_chop20_boundary60_1m | Day of week=Monday | +0.50 | 0.975 |
| NOT VALIDATED | ym_chop20_boundary60_1m | Hourly RSI bucket=rsi_55_70 | +0.23 | 0.591 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions/nulls`


**Stance:** HA overlays = descriptive research only. No size increase. No entry filter. No live gate.
(Nulls: none VALIDATED for deployable size-up; NQ WoM3 = RISK THROTTLE only.)

DSR: `TRL-2026-00178`

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions`
