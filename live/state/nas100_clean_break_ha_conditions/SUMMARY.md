# NAS100 clean-break — HA mill

Source: `live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation` (NAS100 clean-break trail06_m4_e2_out_be 1m-fill unit book (~$+12.3k / N/S 6.23 / 1166; live/public default = ×10)).

Pipeline: profile → filter/1.25×/1.5× overlay → 1.25× matched nulls
(same bar as weekly OD / FBO / CHOP20).
DSR: TRL-2026-00198 (parallel ledger while primary wipe pending).

## Profile

# NAS100 clean-break — HA condition profile

High-probability condition study on **Engine+PaperBroker 1m-fill** tape
(NAS100 clean-break trail06_m4_e2_out_be 1m-fill unit book (~$+12.3k / N/S 6.23 / 1166; live/public default = ×10)).
Features: DOW / week-of-month / Entry month / hour / 5m MA /
hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=40.

## Book

- **NAS100 clean-break trail06_m4_e2_out_be (1m-fill unit)**: n=1166 WR=12.9% avg=$11 net=$12253 N/S=6.57

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| Entry month | April | 86 | 22% | +9.2 | $53 | $+42 | 2.47 |
| Entry month | January | 96 | 19% | +5.9 | $30 | $+19 | 1.66 |
| Day of week | Monday | 261 | 16% | +3.6 | $26 | $+15 | 1.57 |
| Week of month | 4 | 267 | 14% | +1.4 | $21 | $+10 | 0.60 |
| Entry month | August | 105 | 18% | +5.2 | $20 | $+9 | 1.53 |
| Prior-month range half | month_aligned | 301 | 17% | +4.1 | $19 | $+8 | 1.88 |
| ATR14 quartile | atr_q4 | 290 | 14% | +0.9 | $19 | $+8 | 0.42 |
| Week of month | 5 | 89 | 15% | +1.7 | $19 | $+8 | 0.47 |
| 5m MA cross vs trade | cross_aligned | 66 | 14% | +0.8 | $18 | $+8 | 0.18 |
| 5m MA vs trade | ma_aligned | 710 | 13% | +0.5 | $17 | $+7 | 0.32 |
| Week of month | 1 | 269 | 15% | +2.0 | $17 | $+6 | 0.89 |
| Entry month | March | 88 | 15% | +1.9 | $16 | $+5 | 0.52 |
| Hourly RSI bucket | rsi_55_70 | 392 | 13% | +0.4 | $14 | $+4 | 0.21 |
| Entry month | October | 93 | 15% | +2.2 | $14 | $+4 | 0.61 |
| ATR14 quartile | atr_q2 | 290 | 15% | +2.0 | $14 | $+4 | 0.89 |

## Entry month board (appendix)

| month | n | WR | WRΔpp | avg | avgΔ | net | years green |
|---|---:|---:|---:|---:|---:|---:|---:|
| January | 96 | 19% | +5.9 | $30 | $+19 | $+2836 | 8/9 |
| February | 99 | 3% | -9.8 | $-25 | $-35 | $-2426 | 0/9 |
| March | 88 | 15% | +1.9 | $16 | $+5 | $+1369 | 6/9 |
| April | 86 | 22% | +9.2 | $53 | $+42 | $+4536 | 7/9 |
| May | 103 | 10% | -3.2 | $9 | $-2 | $+905 | 4/9 |
| June | 109 | 13% | -0.0 | $13 | $+2 | $+1364 | 4/9 |
| July | 98 | 12% | -0.6 | $13 | $+2 | $+1255 | 6/9 |
| August | 105 | 18% | +5.2 | $20 | $+9 | $+2061 | 7/9 |
| September | 101 | 10% | -3.0 | $-12 | $-23 | $-1260 | 2/9 |
| October | 93 | 15% | +2.2 | $14 | $+4 | $+1340 | 4/8 |
| November | 93 | 11% | -2.1 | $2 | $-9 | $+154 | 4/9 |
| December | 95 | 8% | -4.4 | $1 | $-9 | $+118 | 3/9 |

Hub: `/home/tester/hsm/potions/live/state/nas100_clean_break_ha_conditions/profile`


## Overlay

# NAS100 clean-break — HA overlays

Filter / 1.25× / 1.5× on profile notables vs baseline unit tape.

## Full-tape ranked by ΔN/S

| condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---:|---:|---:|---:|---:|---|
| 5m MA vs trade | ma_aligned | filter | 61% | $+136 | +4.65 | $12389 | 11.21 | live_ready |
| Entry month | April | filter | 7% | $-7717 | +4.10 | $4536 | 10.67 | live_ready |
| Day of week | Monday | size_1.5 | 22% | $+3378 | +1.36 | $15631 | 7.93 | live_ready |
| 5m MA vs trade | ma_aligned | size_1.5 | 61% | $+6195 | +1.29 | $18448 | 7.86 | live_ready |
| Week of month | 1 | size_1.5 | 23% | $+2274 | +1.20 | $14527 | 7.77 | live_ready |
| Entry month | April | size_1.5 | 7% | $+2268 | +1.15 | $14521 | 7.71 | live_ready |
| Week of month | 4 | filter | 23% | $-6775 | +1.01 | $5478 | 7.58 | live_ready |
| Week of month | 4 | size_1.5 | 23% | $+2739 | +0.75 | $14992 | 7.31 | live_ready |
| 5m MA vs trade | ma_aligned | size_1.25 | 61% | $+3097 | +0.72 | $15350 | 7.29 | live_ready |
| Day of week | Monday | size_1.25 | 22% | $+1689 | +0.70 | $13942 | 7.27 | live_ready |
| Day of week | Monday | filter | 22% | $-5497 | +0.62 | $6756 | 7.19 | live_ready |
| Week of month | 1 | size_1.25 | 23% | $+1137 | +0.60 | $13390 | 7.17 | live_ready |
| Entry month | April | size_1.25 | 7% | $+1134 | +0.58 | $13387 | 7.14 | live_ready |
| Entry month | August | size_1.5 | 9% | $+1030 | +0.55 | $13283 | 7.12 | live_ready |
| Week of month | 4 | size_1.25 | 23% | $+1370 | +0.39 | $13622 | 6.96 | live_ready |
| Entry month | August | size_1.25 | 9% | $+515 | +0.28 | $12768 | 6.84 | live_ready |
| 5m MA cross vs trade | cross_aligned | size_1.5 | 6% | $+598 | +0.06 | $12851 | 6.63 | live_ready |
| 5m MA cross vs trade | cross_aligned | size_1.25 | 6% | $+299 | +0.03 | $12552 | 6.60 | live_ready |
| Week of month | 5 | size_1.5 | 8% | $+824 | +0.01 | $13077 | 6.57 | live_ready |
| Week of month | 5 | size_1.25 | 8% | $+412 | +0.00 | $12665 | 6.57 | live_ready |
| Entry month | January | size_1.25 | 8% | $+709 | -0.33 | $12962 | 6.23 | live_ready |
| Entry month | March | size_1.25 | 8% | $+342 | -0.46 | $12595 | 6.11 | live_ready |
| Prior-month range half | month_aligned | size_1.25 | 26% | $+1412 | -0.50 | $13665 | 6.07 | live_ready |
| ATR14 quartile | atr_q4 | size_1.25 | 25% | $+1356 | -0.56 | $13609 | 6.00 | needs_rolling_proxy |
| Entry month | January | size_1.5 | 8% | $+1418 | -0.61 | $13671 | 5.96 | live_ready |
| Entry month | March | size_1.5 | 8% | $+685 | -0.83 | $12938 | 5.73 | live_ready |
| Prior-month range half | month_aligned | size_1.5 | 26% | $+2824 | -0.85 | $15077 | 5.72 | live_ready |
| ATR14 quartile | atr_q4 | size_1.5 | 25% | $+2711 | -0.96 | $14964 | 5.61 | needs_rolling_proxy |
| Week of month | 1 | filter | 23% | $-7705 | -2.64 | $4548 | 3.93 | live_ready |
| Prior-month range half | month_aligned | filter | 26% | $-6605 | -2.91 | $5648 | 3.66 | live_ready |
| ATR14 quartile | atr_q4 | filter | 25% | $-6830 | -3.19 | $5423 | 3.38 | needs_rolling_proxy |
| Entry month | January | filter | 8% | $-9417 | -3.38 | $2836 | 3.18 | live_ready |
| Entry month | August | filter | 9% | $-10192 | -4.51 | $2061 | 2.05 | live_ready |
| 5m MA cross vs trade | cross_aligned | filter | 6% | $-11058 | -4.72 | $1195 | 1.85 | live_ready |
| Week of month | 5 | filter | 8% | $-10604 | -5.27 | $1649 | 1.30 | live_ready |
| Entry month | March | filter | 8% | $-10884 | -5.39 | $1369 | 1.17 | live_ready |

Hub: `/home/tester/hsm/potions/live/state/nas100_clean_break_ha_conditions/overlay`


## Nulls

# NAS100 clean-break — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay
(organic notables — same selection bar as weekly OD / FBO HA mills).

| decision | condition=bucket | hp% | ΔN/S | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|---:|
| RISK THROTTLE | Day of week=Monday | 22% | +0.70 | 0.022 | 0.030 | 0.471 |
| RISK THROTTLE | Week of month=1 | 23% | +0.60 | 0.035 | 0.047 | 0.561 |
| NOT VALIDATED | Entry month=April | 7% | +0.58 | 1.000 | 0.005 | 0.643 |
| NOT VALIDATED | Week of month=4 | 23% | +0.39 | 0.104 | 0.129 | 0.875 |
| NOT VALIDATED | Entry month=August | 9% | +0.28 | 1.000 | 0.211 | 0.983 |
| NOT VALIDATED | 5m MA cross vs trade=cross_aligned | 6% | +0.03 | 0.216 | 0.443 | 1.000 |
| NOT VALIDATED | Week of month=5 | 8% | +0.00 | 0.500 | 0.498 | 1.000 |

Hub: `/home/tester/hsm/potions/live/state/nas100_clean_break_ha_conditions/nulls`

