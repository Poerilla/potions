# NQ liq-run fade — 2 contracts (TP1@open, runner EOM, SL=full 1R)

After first **2 NY trading days**, fade largest |extension| from month open:

- Enter **2** at limit `p_liq`
- SL = **full liq-run** beyond swing (never trailed to BE/half)
- **1** off at month open
- Runner **1** held to **EOM** (no 2R target)
- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before TP1 same-bar

## Results

| Universe | Armed | Fills | TP1 | Runner EOM | Full stop | Stop after TP1 | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 161 | 80 | 40 | 77 | 40 | 25.5% | +123804 | 111209 | 1.11 | 0.24 |
| hp_lookback_or | 118 | 101 | 50 | 26 | 48 | 24 | 26.7% | +64964 | 84231 | 0.77 | 0.18 |

Vs 2c BE+2R (`liq_run_fade_2c_be_2r`): all-months +$120k / N/S 1.19.

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_eom`

Stance: diagnostic path sim (full-SL + EOM runner).
