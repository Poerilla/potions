# NQ 2c half+open — risk sweep $1k / $2k / $3k (1h path)

- Same structure as `liq_run_fade_2c_half_open_r1000` (not 1m broker)
- SL risk $R → stop_pts = R / (2 × $20)
- COVID cut: **pre** = months before 2020-03; **post** = 2020-03 onward

## HP lookback OR

| Risk $ | Era | Fills | Half | Open | Stop | WR | Net $ | Stress $ | N/S | Avg $ |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | full | 101 | 43 | 30 | 70 | 40% | +31652 | 9144 | 3.46 | +313 |
| 1000 | post_covid | 47 | 15 | 8 | 39 | 32% | +21216 | 7822 | 2.71 | +451 |
| 1000 | pre_covid | 54 | 28 | 22 | 31 | 46% | +10436 | 7112 | 1.47 | +193 |
| 2000 | full | 101 | 51 | 38 | 62 | 46% | +18712 | 18144 | 1.03 | +185 |
| 2000 | post_covid | 47 | 19 | 11 | 36 | 36% | +18468 | 13375 | 1.38 | +393 |
| 2000 | pre_covid | 54 | 32 | 27 | 26 | 54% | +244 | 14112 | 0.02 | +5 |
| 3000 | full | 101 | 54 | 39 | 61 | 47% | -26946 | 50362 | -0.54 | -267 |
| 3000 | post_covid | 47 | 20 | 11 | 36 | 36% | -10334 | 35678 | -0.29 | -220 |
| 3000 | pre_covid | 54 | 34 | 28 | 25 | 56% | -16612 | 24188 | -0.69 | -308 |

## All months

| Risk $ | Era | Fills | Half | Open | Stop | WR | Net $ | Stress $ | N/S | Avg $ |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | full | 161 | 68 | 48 | 112 | 37% | +27576 | 12449 | 2.22 | +171 |
| 1000 | post_covid | 63 | 17 | 8 | 55 | 27% | +10122 | 9854 | 1.03 | +161 |
| 1000 | pre_covid | 98 | 51 | 40 | 57 | 44% | +17454 | 10727 | 1.63 | +178 |
| 2000 | full | 161 | 81 | 62 | 97 | 45% | +14399 | 27715 | 0.52 | +89 |
| 2000 | post_covid | 63 | 23 | 13 | 50 | 33% | +17344 | 18218 | 0.95 | +275 |
| 2000 | pre_covid | 98 | 58 | 49 | 47 | 52% | -2946 | 18470 | -0.16 | -30 |
| 3000 | full | 161 | 90 | 68 | 90 | 48% | -21136 | 48193 | -0.44 | -131 |
| 3000 | post_covid | 63 | 26 | 14 | 49 | 35% | -8053 | 36444 | -0.22 | -128 |
| 3000 | pre_covid | 98 | 64 | 54 | 41 | 57% | -13083 | 19178 | -0.68 | -134 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_half_open_risk_sweep`

Stance: HP post-COVID best N/S among {1,2,3}k: **$1000** (N/S 2.71, net +21216). path diagnostic only — no 1m broker yet for this book.
