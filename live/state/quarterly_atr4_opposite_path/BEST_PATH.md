# Quarterly ±4×ATR opposite-path study

Same open-week mid ±ATR(14) levels as the quarterly ATR4 fade model (4h).

**First fade win:** touch ±4, then opposite ±4, **before** same-side ±8.
**Reverse after win:** from that opposite ±4, reach original ±4 before reverse-side ±8.

| Market | Quarters | First touches | First win (→opp4) | Fail (±8) | Unresolved | First WR | Rev after win | Rev win | Rev fail8 | Rev WR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 92 | 91 | 36 | 54 | 1 | 39.6% | 36 | 9 | 24 | 25.0% |
| GBPUSD | 92 | 91 | 39 | 50 | 2 | 42.9% | 39 | 11 | 27 | 28.2% |
| USDJPY | 92 | 91 | 23 | 66 | 2 | 25.3% | 23 | 9 | 13 | 39.1% |
| AUDJPY | 90 | 89 | 25 | 63 | 1 | 28.1% | 25 | 7 | 12 | 28.0% |
| XAUUSD | 92 | 88 | 30 | 57 | 1 | 34.1% | 30 | 11 | 18 | 36.7% |
| XAGUSD | 92 | 85 | 23 | 48 | 14 | 27.1% | 23 | 8 | 12 | 34.8% |
| US30 | 36 | 32 | 13 | 19 | 0 | 40.6% | 13 | 7 | 4 | 53.8% |
| NAS100 | 36 | 33 | 8 | 25 | 0 | 24.2% | 8 | 2 | 6 | 25.0% |
| NQ | 65 | 61 | 16 | 44 | 1 | 26.2% | 16 | 6 | 10 | 37.5% |
| YM | 65 | 61 | 22 | 39 | 0 | 36.1% | 22 | 10 | 10 | 45.5% |

## Highest-WR path + MAE tattoo → risk

Candidates: `first_lower`, `first_upper`, `second_any`, `second_after_lower`, `second_after_upper` (min n=5). Risk = ceil(tattoo MAE/ATR to next 0.5).

| Market | Best path | Mode | Sides | N | WR | Tattoo | MAE | MAE/ATR | Risk |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| EURUSD | second_after_upper | second_only | lower | 17 | 41.2% | 2003 Q4 #1 lower | 0.0091524 | 1.93× | 2.00×ATR |
| GBPUSD | first_lower | first_only | lower | 53 | 58.5% | 2004 Q4 #1 lower | 0.0094292 | 1.96× | 2.00×ATR |
| USDJPY | second_after_lower | second_only | upper | 8 | 50.0% | 2003 Q3 #1 upper | 0.4706 | 1.37× | 1.50×ATR |
| AUDJPY | second_after_lower | second_only | upper | 11 | 36.4% | 2005 Q3 #1 upper | 0.85258 | 2.38× | 2.50×ATR |
| XAUUSD | second_after_upper | second_only | lower | 13 | 53.8% | 2004 Q3 #1 lower | 0.63155 | 0.25× | 0.50×ATR |
| XAGUSD | second_after_lower | second_only | upper | 9 | 44.4% | 2015 Q2 #1 upper | 0.25638 | 1.49× | 1.50×ATR |
| US30 | first_lower | first_only | lower | 11 | 72.7% | 2018 Q2 #1 lower | 58.634 | 0.32× | 0.50×ATR |
| NAS100 | first_lower | first_only | lower | 9 | 55.6% | 2017 Q2 #1 lower | 28.066 | 1.88× | 2.00×ATR |
| NQ | second_after_upper | second_only | lower | 8 | 50.0% | 2013 Q2 #1 lower | 12.4 | 1.13× | 1.50×ATR |
| YM | second_after_upper | second_only | lower | 9 | 55.6% | 2016 Q2 #1 lower | 43.945 | 0.68× | 1.00×ATR |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_opposite_path`

Detail: `quarter_paths.csv`, `path_candidates.csv`, `mae_tattoos.csv`, `best_path.csv`.
