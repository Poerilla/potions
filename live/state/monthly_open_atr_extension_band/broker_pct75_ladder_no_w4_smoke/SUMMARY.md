# NQ monthly open ext band — ladder compare (no week 4, gap-retag)

Engine + PaperBroker **1h**. Entry **pct75**; SL **wide_2.5x**; band **6-mo rolling**.

Entry at min + 75%·(max−min); SL max + 2.5×(max−entry).

- **Skip entry weeks:** 4
- **Gap rule:** void limit fill if prior close is on the approach side and bar opens through the entry; re-arm only after price re-tags the level.
- Ladder: N@band-med / N@month-open / N runner; runner SL → **BE** only after open target.
- Slippage **1** tick · fee **$1.50**/unit · NQ $20/pt

## Risk-adjusted comparison

| Ladder | Qty | Trades | Net $ | Net@10 | Stress $ | N/S | N/S@10 | Sharpe | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3_3_3 | 9 | 73 | 664,710 | 738,566 | -387,092 | 1.72 | 1.72 | 0.06 | 1.80 |

## Verdict

- Best **N/S@10**: `3_3_3` (1.72)
- Best **net@10**: `3_3_3` ($738,566)

Stance: research — compare ladders under gap-retag + no week 4 before promote.

