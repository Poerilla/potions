# NQ liq-run fade — 2 contracts (TP1@open→+0.5R stop, runner 2R)

After first **2 NY trading days**, fade largest |extension| from month open:

- Enter **2** at limit `p_liq`
- Initial SL = 1R beyond swing
- **1** off at month open → stop to **+0.5R** (½ liq-run from entry)
- Runner **1** to **2R** (entry ± 2×liq-run)
- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before targets same-bar

## Results

| Universe | Armed | Fills | TP1 | TP2 | Full stop | Half stop | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 161 | 80 | 23 | 77 | 56 | 50.3% | +106932 | 114634 | 0.93 | 0.24 |
| hp_lookback_or | 118 | 101 | 50 | 14 | 48 | 35 | 50.5% | +52206 | 87682 | 0.60 | 0.16 |

Vs 2c BE+2R (`liq_run_fade_2c_be_2r`): all-months +$120k / N/S 1.19.

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_half_2r`

Stance: diagnostic path sim (half-R trail overlay).
