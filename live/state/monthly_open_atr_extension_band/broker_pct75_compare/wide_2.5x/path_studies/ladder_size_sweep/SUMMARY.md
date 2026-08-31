# Ladder size sweep (wide_2.5x, **no week 4**)

Question: does bucket size **3** beat **5** for turning more trades into winners?
Structure: N @ band-med / N @ month-open / N runner; SL→BE only after open target.

Book: **53** trades (week 4 dropped). Flat 10-lot: **31** wins (58.5%), net **$620,936**.

## Equal thirds N/N/N

| Ladder | Total | Wins | Win% | Losers→wins | Wins→losses | Net new | Net (norm→10) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1/1/1 | 3 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 2/2/2 | 6 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 3/3/3 | 9 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 4/4/4 | 12 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 5/5/5 | 15 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 6/6/6 | 18 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 7/7/7 | 21 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |
| 8/8/8 | 24 | 33/53 | 62.3% | 2 | 0 | +2 | $884,199 |

## 3 vs 5

- **3/3/3**: 33 wins (62.3%), losers→wins **2**, wins→losses **0**, size-norm net **$884,199**
- **5/5/5**: 33 wins (62.3%), losers→wins **2**, wins→losses **0**, size-norm net **$884,199**

- Flips unique to **3/3/3**: 0 · unique to **5/5/5**: 0 · both: 2

**Read:** win count is driven by *path* (hit med / open / BE), not by N — equal thirds share the same hit logic, so **win% is identical across N/N/N**; only $ scales with size. To change *who* wins, need different **weights** (more at med vs runner), not a different equal N.

## Asymmetric weights (no week 4) — can change winners

| Ladder | Wins | Win% | Net new winners | Net (norm→10) |
|---|---:|---:|---:|---:|
| 6/2/2 | 34/53 | 64.2% | +3 | $798,696 |
| 2/2/5 | 33/53 | 62.3% | +2 | $985,357 |
| 3/2/5 | 33/53 | 62.3% | +2 | $953,866 |
| 2/3/4 | 33/53 | 62.3% | +2 | $941,669 |
| 2/4/3 | 33/53 | 62.3% | +2 | $897,981 |
| 5/5/5 | 33/53 | 62.3% | +2 | $884,199 |
| 1/1/1 | 33/53 | 62.3% | +2 | $884,199 |
| 2/2/2 | 33/53 | 62.3% | +2 | $884,199 |
| 3/3/3 | 33/53 | 62.3% | +2 | $884,199 |
| 4/4/4 | 33/53 | 62.3% | +2 | $884,199 |
| 6/6/6 | 33/53 | 62.3% | +2 | $884,199 |
| 7/7/7 | 33/53 | 62.3% | +2 | $884,199 |
| 8/8/8 | 33/53 | 62.3% | +2 | $884,199 |
| 2/5/2 | 33/53 | 62.3% | +2 | $854,292 |
| 3/5/2 | 33/53 | 62.3% | +2 | $835,907 |

- Most wins: **6/2/2** (34, 64.2%)
- Best size-norm net: **1/1/7** ($1,086,516)

Stance: diagnostic pandas. Prefer a weight that maximizes wins *or* norm net before broker-like.
Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/broker_pct75_compare/wide_2.5x/path_studies/ladder_size_sweep`

