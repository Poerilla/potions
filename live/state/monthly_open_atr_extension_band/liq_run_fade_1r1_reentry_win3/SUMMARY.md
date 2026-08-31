# NQ liq-run fade — base 1:1 + win-only re-entry (max 3)

After first **2 NY trading days**, fade largest |extension| from month open:

- **Limit** at `p_liq` (qty **10**); **target** = month open; **SL** = full 1R
- Re-arm **only after a win (target)**, on leave-open then **re-touch open**
- **Max 3 re-entries** (≤4 fills/month); no re-arm after stop/EOM
- Path-aware 1h; 1-tick slip; fee $1.50/side; stop before target same-bar

## Results

| Universe | Months | Fills | Re-entries | Target | Stop | EOM | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 216 | 55 | 103 | 104 | 9 | 49.5% | +710020 | 487170 | 1.46 | 0.26 |
| hp_lookback_or | 118 | 136 | 35 | 66 | 63 | 7 | 51.5% | +555570 | 352410 | 1.58 | 0.28 |

Vs unlimited open-touch re-entry (`liq_run_fade_1r1_reentry`): all +$711k / N/S 1.78; HP +$618k / N/S 2.24.

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_win3`

Stance: diagnostic path sim (win-only re-entry cap).
