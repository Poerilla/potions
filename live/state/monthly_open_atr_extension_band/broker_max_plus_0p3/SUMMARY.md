# NQ monthly open extension band — max broker-like compare

Engine + PaperBroker on **1h** bars. Entry **max**; band **6-month rolling**.


Entry at mean(max); SL max + 30% of band width.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt
- Qty: **10** per entry · target = month open

## Risk-adjusted comparison

| SL mode | Trades | Net $ | Stress DD $ | N/S | Sharpe | Sortino | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| plus_0.3 | 57 | 237,812 | -382,935 | 0.62 | 0.03 | 0.00 | 0.69 |

## Verdict

- Best **N/S**: `plus_0.3` (0.62)
- Best **Sharpe**: `plus_0.3` (0.03)

Pandas diagnostic hubs (no spread/slip): `variants/max/`.

