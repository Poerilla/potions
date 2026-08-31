# NQ monthly open extension band — max broker-like compare

Engine + PaperBroker on **1h** bars. Entry **max**; band **6-month rolling**.

Entry trigger **traverse_reclaim**: 1h close through band entry, then reverse and 1h close back in favour (long: close>entry & bullish; short: close<entry & bearish) → market.


Entry at mean(max); SL max + 30% of band width.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt
- Qty: **10** per entry · target = month open

## Risk-adjusted comparison

| SL mode | Trades | Net $ | Stress DD $ | N/S | Sharpe | Sortino | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| plus_0.3 | 64 | 517,402 | -335,279 | 1.54 | 0.06 | 0.02 | 1.54 |

## Verdict

- Best **N/S**: `plus_0.3` (1.54)
- Best **Sharpe**: `plus_0.3` (0.06)

Pandas diagnostic hubs (no spread/slip): `variants/max/`.

Vs resting-limit baseline (`broker_max_plus_0p3`): net +$238k, N/S **0.62** → reclaim **N/S 1.54**.

Stance: research — reclaim entry helps on same SL.
