# NQ liq-run fade — 3c (1/1/1), $1000 risk, half + open + runner

After first **2 NY trading days**, fade largest |extension| from month open:

- Enter **3** at `p_liq`
- SL = **$1000** risk (16.67 pts @ 3×$20/pt)
- **1** off at halfway (mid entry↔month open)
- **1** off at month open
- **1** runner to **2R** or **3R** (R = initial stop pts)
- Optional **BE** stop when half leg fills
- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before targets

## Baseline (2c half+open, same hub family)

| Universe | Fills | Half | Open | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| all_months | 161 | 68 | 48 | +27576 | 12449 | 2.22 | 0.31 |
| hp_lookback_or | 101 | 43 | 30 | +31652 | 9144 | 3.46 | 0.49 |

## All months

| Variant | Fills | Half | Open | Runner | Stop | BE stop | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| half_open_2r | 161 | 47 | 32 | 28 | 133 | 0 | -28451 | 29052 | -0.98 | -0.34 |
| half_open_3r | 161 | 47 | 32 | 26 | 135 | 0 | -21784 | 23468 | -0.93 | -0.25 |
| half_open_2r_be | 161 | 47 | 20 | 20 | 141 | 27 | -31221 | 30500 | -1.02 | -0.39 |
| half_open_3r_be | 161 | 47 | 20 | 18 | 143 | 29 | -26554 | 25834 | -1.03 | -0.32 |

## HP lookback

| Variant | Fills | Half | Open | Runner | Stop | BE stop | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| half_open_2r | 101 | 30 | 20 | 18 | 83 | 0 | -8945 | 22794 | -0.39 | -0.15 |
| half_open_3r | 101 | 30 | 20 | 16 | 85 | 0 | -5612 | 22794 | -0.25 | -0.09 |
| half_open_2r_be | 101 | 30 | 13 | 13 | 88 | 17 | -9755 | 21563 | -0.45 | -0.17 |
| half_open_3r_be | 101 | 30 | 13 | 11 | 90 | 19 | -7422 | 20563 | -0.36 | -0.13 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_3c_half_open_runner_r1000`

Stance: diagnostic 1/1/1 scale-out vs 2c baseline; compare BE overlay.
