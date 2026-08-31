# NQ liquidity-run fade — base 1:1 + open-touch re-entry

After first **2 NY trading days**, fade largest |extension| from month open:

- **Limit** at liq swing `p_liq` (qty **10**)
- **Target** = month open; **SL** = full liq-run size (never trailed)
- After exit: re-arm when price **touches month open** again
- After target @ open: must leave open, then re-touch, before re-arm
- Path-aware 1h; 1-tick slip; fee $1.50/side; stop before target same-bar

## Results

| Universe | Months | Fills | Re-entries | Target | Stop | EOM | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 259 | 98 | 123 | 125 | 11 | 49.4% | +711280 | 400070 | 1.78 | 0.23 |
| hp_lookback_or | 118 | 164 | 63 | 82 | 75 | 7 | 52.4% | +618030 | 276150 | 2.24 | 0.28 |

Vs base once-per-month (`liq_run_fade_1r1`): all-months ~+$532k / N/S 0.96.

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry`

Stance: diagnostic path sim (base + open-touch re-entry).
