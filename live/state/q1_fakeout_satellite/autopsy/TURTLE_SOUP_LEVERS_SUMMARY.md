# Turtle soup levers + stop-out autopsy + scale-in

## Winner MAE (baseline R/5 book, used for scale-in width)

- mean MAE of winners: **1.91 pts** (n=34)
- median MAE of winners: **1.00 pts**
- baseline avg stop distance: ~R/5 (mean risk on fills in baseline study ~4.3 pts)

## Stop-out autopsy (baseline full stops — could they have won?)

After the full stop was hit, first subsequent touch:

| Cause | N | % |
|---|---:|---:|
| invalidation_continuation | 86 | 78.9 |
| chop_neither | 13 | 11.9 |
| shakeout_would_reach_opp_OR | 10 | 9.2 |

Of shakeouts that would reach opp OR: 10; of those also hit opp 1R: 0.

## Lever grid (all BE-after-scale, runner opp 1R)

| variant | sessions | fills | fill_rate_pct | avg_filled_qty | full_stop | scaled_4 | scale_rate_pct | win_pct | net_usd | usd_per_fill | profit_factor | avg_risk_usd | neg_years | n_years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stop_R5 | 203 | 143 | 70.4 | 5.0 | 109 | 31 | 21.7 | 23.8 | 42637.5 | 298.16 | 1.886 | 433.36 | 7 | 16 |
| floor_2ticks_R5 | 203 | 143 | 70.4 | 5.0 | 109 | 31 | 21.7 | 23.8 | 42632.5 | 298.13 | 1.886 | 433.39 | 7 | 16 |
| floor_4ticks_R5 | 203 | 143 | 70.4 | 5.0 | 109 | 31 | 21.7 | 23.8 | 42352.5 | 296.17 | 1.875 | 435.8 | 8 | 16 |
| floor_6ticks_R5 | 203 | 143 | 70.4 | 5.0 | 107 | 32 | 22.4 | 24.5 | 42337.5 | 296.07 | 1.857 | 446.54 | 7 | 16 |
| floor_8ticks_R5 | 203 | 143 | 70.4 | 5.0 | 106 | 33 | 23.1 | 25.2 | 41152.5 | 287.78 | 1.801 | 465.91 | 8 | 16 |
| stop_R6 | 203 | 143 | 70.4 | 5.0 | 112 | 29 | 20.3 | 21.7 | 40680.83 | 284.48 | 1.984 | 361.85 | 7 | 16 |
| filt_break_before_1000 | 173 | 128 | 74.0 | 5.0 | 98 | 27 | 21.1 | 23.4 | 39640.0 | 309.69 | 1.957 | 423.13 | 8 | 16 |
| scalein_mae_median | 203 | 143 | 70.4 | 4.78 | 111 | 25 | 17.5 | 22.4 | 37452.0 | 261.9 | 1.865 | 421.63 | 8 | 16 |
| filt_wick_ge_0.25R | 161 | 108 | 67.1 | 5.0 | 83 | 22 | 20.4 | 23.1 | 36715.0 | 339.95 | 2.163 | 387.04 | 6 | 15 |
| combo_wick25_floor4 | 161 | 108 | 67.1 | 5.0 | 83 | 22 | 20.4 | 23.1 | 36430.0 | 337.31 | 2.144 | 390.09 | 6 | 15 |
| stop_R4 | 203 | 143 | 70.4 | 5.0 | 106 | 33 | 23.1 | 25.2 | 34618.75 | 242.09 | 1.582 | 541.7 | 7 | 16 |
| buf_2ticks_R5 | 203 | 137 | 67.5 | 5.0 | 110 | 25 | 18.2 | 19.7 | 34427.5 | 251.3 | 1.714 | 441.75 | 8 | 16 |
| buf_2_floor4 | 203 | 137 | 67.5 | 5.0 | 109 | 25 | 18.2 | 19.7 | 34222.5 | 249.8 | 1.707 | 444.16 | 8 | 16 |
| buf_1ticks_R5 | 203 | 139 | 68.5 | 5.0 | 110 | 26 | 18.7 | 20.9 | 33377.5 | 240.13 | 1.691 | 437.37 | 7 | 16 |
| scalein_mae_mean | 203 | 143 | 70.4 | 4.69 | 112 | 23 | 16.1 | 21.7 | 33142.01 | 231.76 | 1.822 | 414.5 | 10 | 16 |
| scalein_mae_mean_floor4 | 203 | 143 | 70.4 | 4.69 | 112 | 23 | 16.1 | 21.7 | 32905.51 | 230.11 | 1.813 | 416.66 | 10 | 16 |
| filt_wick_ge_0.25R_and_before_1000 | 140 | 99 | 70.7 | 5.0 | 77 | 19 | 19.2 | 22.2 | 31532.5 | 318.51 | 2.12 | 377.73 | 7 | 15 |
| combo_wick25_floor4_scalein | 161 | 108 | 67.1 | 4.71 | 86 | 15 | 13.9 | 20.4 | 29250.37 | 270.84 | 2.113 | 371.8 | 9 | 15 |
| buf_4ticks_R5 | 203 | 134 | 66.0 | 5.0 | 109 | 20 | 14.9 | 17.9 | 26950.0 | 201.12 | 1.556 | 443.06 | 8 | 16 |
| stop_R8 | 203 | 143 | 70.4 | 5.0 | 122 | 19 | 13.3 | 14.7 | 22550.0 | 157.69 | 1.665 | 270.85 | 6 | 16 |
| filt_wick_ge_0.5R | 54 | 31 | 57.4 | 5.0 | 25 | 5 | 16.1 | 19.4 | 9037.5 | 291.53 | 2.104 | 351.94 | 7 | 12 |
## Wider stops (extra pass)

| Variant | Net | PF | Scale% | Avg risk | Neg years | Pre-2021 net |
|---|---:|---:|---:|---:|---:|---:|
| R/5 (baseline) | $42.6k | 1.89 | 21.7 | $433 | 7/16 | ~$12.1k |
| ~R/3 (frac 0.30) | $27.0k | 1.39 | 23.1 | $650 | 8/16 | $10.0k |
| **2×R/5 (frac 0.40)** | **$48.7k** | 1.61 | 26.6 | $867 | 8/16 | $6.6k |
| R/2 (frac 0.50) | $44.7k | 1.47 | 28.7 | $1,083 | 9/16 | $4.2k |

2×R/5 lifts net by catching more shakeouts but **doubles dollar risk**, cuts PF, and shifts edge into post-2021 — pre-2021 gets worse. Not a free lunch.

## Verdict

1. **Stop-out autopsy:** of 109 full stops, **79% are true invalidation** (original break resumes). Only **10 (9%)** later reach the opposite OR — and **0/10** reach opp 1R. Most stop-outs could *not* have been winners; widening the stop to chase the 10 costs real money on the 86.
2. **Tick floors / entry buffers:** no meaningful lift. R/5 already exceeds 4 ticks on most q1 ORs; souping deeper (buffer) just cuts fills and PF.
3. **Wick filter (≥0.25R beyond OR):** best *quality* lever — PF **2.16**, 6 neg years / 15, but fewer trades and lower net ($36.7k). Worth keeping as a quality gate.
4. **Scale-in across winner MAE (~1.9 pts):** avg filled qty drops only to **4.7** (losers usually blast through the whole ladder), net and stability both worsen (10 neg years). Does **not** reduce risk the way we hoped — winners barely dip, losers don't pause in the MAE window.
5. **Keep for deeper work:** baseline R/5 geometry + optional `wick ≥ 0.25R` filter. Scale-in and stop-widening are dead ends on this sample.
