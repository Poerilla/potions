# Adaptive 50/150 scaleout monthly-bias re-sim

This is the stricter version of the monthly-bias test: the gate is applied before each candidate leg is simulated, so same-day chaining uses only trades that would actually have been taken.

## Headline

- Baseline: 1,831 legs, $30,218.50, trade DD $-7,498.00, gross contract-points 17,855.75.
- Baseline split: v2b alone was $35,847.00 with $-5,190.00 DD; v2d alone was $-5,628.50 with $-12,127.00 DD.
- Monthly outside-only: 1,079 legs, $24,568.50, trade DD $-6,357.00, gross contract-points 13,902.75.
- Best non-diagnostic split here: keep v2b unchanged, require v2d to align with monthly bias: 1,563 legs, $35,903.00, trade DD $-5,190.00, gross contract-points 20,296.00.

## Metrics

| Segment | Trades | Days | Net | Gross pts | Net pt equiv | Trade DD | Daily DD | Win rate | PF | TP1 | TP2 | Avg/trade |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1831 | 1281 | $30,218.50 | 17,855.75 | 15,109.25 | $-7,498.00 | $-7,470.50 | 53.69% | 1.12 | 46.04% | 18.02% | $16.50 |
| baseline_v2b_only_split | 1430 | 958 | $35,847.00 | 20,068.50 | 17,923.50 | $-5,190.00 | $-4,958.00 | 55.03% | 1.19 | 46.64% | 18.67% | $25.07 |
| baseline_v2d_only_split | 401 | 323 | $-5,628.50 | -2,212.75 | -2,814.25 | $-12,127.00 | $-12,099.50 | 48.88% | 0.92 | 43.89% | 15.71% | $-14.04 |
| monthly_outside_only | 1079 | 762 | $24,568.50 | 13,902.75 | 12,284.25 | $-6,357.00 | $-6,278.00 | 55.42% | 1.17 | 47.08% | 19.37% | $22.77 |
| monthly_aligned_only | 547 | 547 | $7,693.00 | 4,667.00 | 3,846.50 | $-8,738.00 | $-8,738.00 | 56.49% | 1.11 | 47.35% | 16.45% | $14.06 |
| monthly_opposed_only | 578 | 578 | $16,567.00 | 9,150.50 | 8,283.50 | $-7,205.50 | $-7,205.50 | 54.15% | 1.21 | 47.23% | 21.80% | $28.66 |
| v2b_outside_only_v2d_unchanged | 1242 | 892 | $22,234.50 | 12,980.25 | 11,117.25 | $-7,063.00 | $-7,063.00 | 54.59% | 1.13 | 46.94% | 18.60% | $17.90 |
| v2d_outside_only_v2b_unchanged | 1668 | 1151 | $32,552.50 | 18,778.25 | 16,276.25 | $-6,800.00 | $-6,449.50 | 54.14% | 1.14 | 46.04% | 18.47% | $19.52 |
| v2d_aligned_only_v2b_unchanged | 1563 | 1091 | $35,903.00 | 20,296.00 | 17,951.50 | $-5,190.00 | $-4,958.00 | 55.02% | 1.17 | 46.77% | 18.36% | $22.97 |
| v2d_opposed_only_v2b_unchanged | 1581 | 1109 | $32,668.00 | 18,705.50 | 16,334.00 | $-8,391.00 | $-8,215.50 | 54.08% | 1.15 | 46.11% | 18.72% | $20.66 |
| diagnostic_v2b_opposed_v2d_aligned | 560 | 560 | $19,802.00 | 10,741.00 | 9,901.00 | $-4,078.50 | $-4,078.50 | 56.79% | 1.26 | 49.11% | 20.89% | $35.36 |

## Outputs

- Re-sim legs: [adaptive_scaleout_monthly_bias_resim_legs.csv](adaptive_scaleout_monthly_bias_resim_legs.csv)
- Summary CSV: [adaptive_scaleout_monthly_bias_resim_summary.csv](adaptive_scaleout_monthly_bias_resim_summary.csv)
- Skip audit: [adaptive_scaleout_monthly_bias_resim_skips.csv](adaptive_scaleout_monthly_bias_resim_skips.csv)

## Notes

- The monthly state is still causal: trade day uses the prior daily close versus the first 3 daily bars of the month.
- This does not change the scaleout stop/target mechanics; it only gates whether a candidate adaptive leg is allowed to enter.
