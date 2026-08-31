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
| 3_3_3 | 9 | 71 | 650,945 | 723,272 | -387,092 | 1.68 | 1.68 | 0.05 | 1.76 |
| 6_2_2 | 10 | 71 | 644,538 | 644,538 | -410,194 | 1.57 | 1.57 | 0.05 | 1.65 |
| 1_1_7 | 9 | 71 | 822,294 | 913,660 | -475,118 | 1.73 | 1.73 | 0.05 | 1.74 |
| 2_2_5 | 9 | 71 | 736,619 | 818,466 | -416,954 | 1.77 | 1.77 | 0.06 | 1.84 |
| 2_5_3 | 10 | 71 | 725,206 | 725,206 | -425,125 | 1.71 | 1.71 | 0.05 | 1.79 |

## Verdict

- Best **N/S@10**: `2_2_5` (1.77)
- Best **net@10**: `1_1_7` ($913,660)

Stance: research — compare ladders under gap-retag + no week 4 before promote.

