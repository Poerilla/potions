# Prior-opposed open ±4×ATR opposite-path (5m, non-HA)

Universe: profitable prior-opposed books only.
Levels: **session open price** ± k×ATR(14) on continuous **5m** OHLC (not Heikin Ashi).
ATR known at open = prior completed 5m Wilder ATR.
Days = campaign entry days from each book's fills.

**First fade win:** touch ±4, then opposite ±4, **before** same-side ±8.
**Reverse after win:** from opposite ±4, reach original ±4 before reverse-side ±8.

| Book | Symbol | Variant | PO N/S | Days | Touches | First→opp4 | Fail±8 | Unres | First WR | Rev win | Rev WR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nq_rl | NQ | resting_limit_S_1_1_3 | 19.40 | 419 | 418 | 112 | 253 | 53 | 26.8% | 25 | 22.3% |
| mnq_rl | MNQ | resting_limit_S_1_1_3 | 18.44 | 416 | 415 | 112 | 248 | 55 | 27.0% | 24 | 21.4% |
| ym_rl | YM | resting_limit_S_1_1_3 | 8.53 | 421 | 410 | 118 | 235 | 57 | 28.8% | 25 | 21.2% |
| mym_rl | MYM | resting_limit_S_1_1_3 | 6.47 | 407 | 398 | 115 | 229 | 54 | 28.9% | 20 | 17.4% |
| us30_london | US30 | london_prior_opposed_S_1_1_3 | 6.23 | 294 | 294 | 95 | 196 | 3 | 32.3% | 19 | 20.0% |
| nas100_london | NAS100 | london_prior_opposed_S_1_1_3 | 8.38 | 322 | 320 | 116 | 198 | 6 | 36.2% | 34 | 29.3% |

## Best path (max WR, n≥5); exists if WR≥50%

| Book | Symbol | Best path | Mode | Sides | N | WR | Exists | Risk |
|---|---|---|---|---|---:|---:|---|---:|
| nq_rl | NQ | first_upper | first_only | upper | 189 | 31.2% | no | 1.00×ATR |
| mnq_rl | MNQ | first_upper | first_only | upper | 188 | 31.4% | no | 2.50×ATR |
| ym_rl | YM | first_upper | first_only | upper | 202 | 33.7% | no | 2.00×ATR |
| mym_rl | MYM | first_upper | first_only | upper | 193 | 33.7% | no | 2.00×ATR |
| us30_london | US30 | first_upper | first_only | upper | 157 | 36.9% | no | 1.00×ATR |
| nas100_london | NAS100 | first_upper | first_only | upper | 165 | 41.2% | no | 2.50×ATR |

Hub: `/home/tester/hsm/potions/live/state/prior_opposed_open_atr4_path`

Detail: `day_paths.csv`, `path_candidates.csv`, `mae_tattoos.csv`, `best_path.csv`.
