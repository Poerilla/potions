# NQ liquidity-run fade — base structure (1:1)

After first **2 NY trading days**, fade the largest |extension| from month open:

- **Limit** at liq swing `p_liq`
- **Target** = month open
- **Stop** = one liq-run beyond the swing (1R = extension)
- Path-aware **1h** OHLC; 1-tick adverse slip; fee $1.50/side; qty **10**
- Same-bar: stop before target

## Results

| Universe | Armed | Fills | Target | Stop | EOM | WR | Net $ | Stress $ | N/S | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_months | 193 | 161 | 80 | 77 | 4 | 50.3% | +531770 | 554980 | 0.96 | 0.24 |
| hp_lookback_or | 118 | 101 | 50 | 48 | 3 | 50.5% | +269470 | 420220 | 0.64 | 0.17 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1`

Stance: **base structure** — diagnostic path sim (not Engine+PaperBroker promote gate).
