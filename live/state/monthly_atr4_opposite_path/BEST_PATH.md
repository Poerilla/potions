# Quarterly ±4×ATR opposite-path study

Same open-week mid ±ATR(14) levels as the quarterly ATR4 fade model (4h).

**First fade win:** touch ±4, then opposite ±4, **before** same-side ±8.
**Reverse after win:** from that opposite ±4, reach original ±4 before reverse-side ±8.

| Market | Quarters | First touches | First win (→opp4) | Fail (±8) | Unresolved | First WR | Rev after win | Rev win | Rev fail8 | Rev WR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 275 | 272 | 85 | 185 | 2 | 31.2% | 85 | 26 | 56 | 30.6% |
| GBPUSD | 275 | 272 | 80 | 191 | 1 | 29.4% | 80 | 24 | 54 | 30.0% |
| USDJPY | 275 | 273 | 85 | 180 | 8 | 31.1% | 85 | 24 | 56 | 28.2% |
| AUDJPY | 268 | 266 | 84 | 174 | 8 | 31.6% | 84 | 24 | 51 | 28.6% |
| XAUUSD | 275 | 264 | 72 | 187 | 5 | 27.3% | 72 | 17 | 49 | 23.6% |
| XAGUSD | 274 | 235 | 58 | 137 | 40 | 24.7% | 58 | 12 | 39 | 20.7% |
| US30 | 106 | 103 | 32 | 70 | 1 | 31.1% | 32 | 11 | 21 | 34.4% |
| NAS100 | 108 | 104 | 28 | 76 | 0 | 26.9% | 28 | 6 | 20 | 21.4% |
| NQ | 193 | 188 | 62 | 126 | 0 | 33.0% | 62 | 14 | 45 | 22.6% |
| YM | 192 | 187 | 56 | 130 | 1 | 29.9% | 56 | 17 | 37 | 30.4% |

## Highest-WR path + MAE tattoo → risk

Candidates: `first_lower`, `first_upper`, `second_any`, `second_after_lower`, `second_after_upper` (min n=5). Risk = ceil(tattoo MAE/ATR to next 0.5).

| Market | Best path | Mode | Sides | N | WR | Tattoo | MAE | MAE/ATR | Risk |
|---|---|---|---|---:|---:|---|---:|---:|---:|
| EURUSD | second_after_upper | second_only | lower | 41 | 34.1% | 2004 Q3 #1 lower | 0.00059479 | 0.18× | 0.50×ATR |
| GBPUSD | second_after_lower | second_only | upper | 41 | 36.6% | 2004 Q9 #1 upper | 0.0035844 | 1.28× | 1.50×ATR |
| USDJPY | first_upper | first_only | upper | 139 | 33.1% | 2003 Q9 #1 upper | 0.065473 | 0.29× | 0.50×ATR |
| AUDJPY | second_after_upper | second_only | lower | 48 | 37.5% | 2003 Q12 #1 lower | 0.14835 | 0.87× | 1.00×ATR |
| XAUUSD | first_lower | first_only | lower | 114 | 35.1% | 2003 Q10 #1 lower | 3.2692 | 1.78× | 2.00×ATR |
| XAGUSD | second_after_lower | second_only | upper | 23 | 34.8% | 2010 Q5 #1 upper | 0.22626 | 0.88× | 1.00×ATR |
| US30 | second_after_upper | second_only | lower | 19 | 42.1% | 2017 Q5 #1 lower | 42.776 | 1.81× | 2.00×ATR |
| NAS100 | first_lower | first_only | lower | 44 | 43.2% | 2017 Q3 #1 lower | 3.9587 | 0.53× | 1.00×ATR |
| NQ | first_lower | first_only | lower | 79 | 38.0% | 2010 Q10 #1 lower | 13.328 | 2.06× | 2.50×ATR |
| YM | second_after_upper | second_only | lower | 36 | 36.1% | 2010 Q8 #1 lower | 104.75 | 2.94× | 3.00×ATR |

Hub: `/home/tester/hsm/potions/live/state/monthly_atr4_opposite_path`

Detail: `quarter_paths.csv`, `path_candidates.csv`, `mae_tattoos.csv`, `best_path.csv`.
