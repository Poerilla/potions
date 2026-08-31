# NQ liq-run fade — 2 contracts (TP1@open→BE, runner 2R)

After first **2 NY trading days**, fade largest |extension| from month open:

- Enter **2** at limit `p_liq`
- Initial SL = 1R beyond swing
- **1** off at month open → stop to **BE**
- Runner **1** to **2R** (entry ± 2×liq-run)
- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before targets same-bar

## Results

| Universe | Armed | Fills | TP1 | TP2 | Full stop | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 161 | 80 | 40 | 77 | 50.3% | +120094 | 101151 | 1.19 | 0.26 |
| hp_lookback_or | 118 | 101 | 50 | 25 | 48 | 50.5% | +75709 | 74199 | 1.02 | 0.23 |

Vs flat 10×1R book (`liq_run_fade_1r1`): all-months ~+$532k / N/S 0.96.

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_be_2r`

Stance: diagnostic path sim (base scale-out overlay).
