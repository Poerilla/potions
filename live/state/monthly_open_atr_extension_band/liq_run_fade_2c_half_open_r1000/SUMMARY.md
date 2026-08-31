# NQ liq-run fade — 2c, $1000 risk, half + open

After first **2 NY trading days**, fade largest |extension| from month open:

- Enter **2** at `p_liq`
- SL = **$1000** risk (25.0 pts @ 2×$20/pt)
- **1** off at halfway (mid entry↔month open)
- **1** off at month open
- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before targets

## Results

| Universe | Armed | Fills | Half | Open | Stop | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 161 | 68 | 48 | 112 | 37.3% | +27576 | 12449 | 2.22 | 0.31 |
| hp_lookback_or | 118 | 101 | 43 | 30 | 70 | 39.6% | +31652 | 9144 | 3.46 | 0.49 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_half_open_r1000`

Stance: diagnostic path sim (small-SL scale-out).
