# US30 band-max fade — SL max+50% band · open TP + runner 2R

Engine + PaperBroker **1h**. Entry **max**; SL **plus_0.5**; band **6-mo rolling**.

Entry at mean(max); SL max + 50% of band width.

- Ladder: **0** @ band-med / **5** @ month-open / **5** runner
- On open fill: runner SL → **BE**; runner TP = month-open ± **2R** (R = entry→stop)
- Gap rule: void gap-through entry; require retag
- Compare: **all weeks** vs **skip week 4**

- Slippage: **1** tick · fee **$1.50**/unit · DSR `TRL-2026-00128`

## Comparison

| Variant | Skip w4 | Trades | Net $ | Stress DD | N/S | Sharpe | Sortino | Calmar |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| all_weeks | no | 26 | 1,527 | -45,417 | 0.03 | 0.00 | 0.00 | 0.03 |
| no_w4 | yes | 24 | 11,518 | -38,323 | 0.30 | 0.02 | 0.01 | 0.31 |

## Verdict

- Best **N/S**: `no_w4` (0.30)
- Prior max+30% flat (no runner): net +$238k, N/S **0.62**
- pct75 wide_2.5x ref: N/S ~**1.31**
- **Skip week 4 did not help** here (lower net and N/S).

Stance: research / lean reject vs pct75 wide_2.5x (N/S ~1.31).

