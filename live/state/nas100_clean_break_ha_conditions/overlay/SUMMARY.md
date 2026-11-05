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
