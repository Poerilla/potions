# Quarterly ATR4 ladder — runner-heavy sizing sweep

Stress top-5 books; ladder ATR rungs fixed (+2/+4/+6/+8); only contract
allocation changes. Runner-heavy cells target residual ≥8.

Contribution priors (board +PnL share): flatten 30.8% · tp4 24.9% · tp3 19.9% · tp2 16.0% · tp1 8.5%.

`net_per_10ct` / `ns_risk_norm` scale PnL & stress to a 10-contract entry so larger books are comparable to baseline `2/2/2/2/2`.

## Per-market ranking (by ns_risk_norm)

### GBPUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `0/0/2/4/8` | 14 | $676,997 | $0 | 5.31 | $483,570 | 0.00 | 34% | only +6/+8 + runner |
| `0/1/2/3/8` | 14 | $664,746 | $0 | 5.27 | $474,818 | 0.00 | 35% | drop weakest contrib (tp1) |
| `0/1/3/4/8` | 16 | $758,552 | $0 | 6.01 | $474,095 | 0.00 | 36% | rounded board contrib shares @ total=16 (runner≥8) |
| `0/3/4/5/8` | 20 | $932,422 | $0 | 7.27 | $466,211 | 0.00 | 39% | rounded board contrib shares @ total=20 (runner≥8) |
| `1/1/2/2/12` | 18 | $824,997 | $0 | 4.36 | $458,331 | 0.00 | 34% | runner=12 |
| `1/1/1/2/10` | 15 | $687,268 | $0 | 4.36 | $458,179 | 0.00 | 34% | runner=10 |
| `1/2/2/3/10` | 18 | $821,106 | $0 | 5.20 | $456,170 | 0.00 | 37% | contrib-shaped; runner=10 |
| `1/2/3/4/8` | 18 | $818,709 | $0 | 6.49 | $454,838 | 0.00 | 39% | steeper back-weight + runner=8 |
| `1/2/2/3/8` | 16 | $724,902 | $0 | 5.74 | $453,064 | 0.00 | 38% | contrib-shaped among scales; runner=8 (~share-weighted) |
| `1/1/2/2/8` | 14 | $632,588 | $0 | 5.01 | $451,848 | 0.00 | 37% | mild back-load; runner=8 |
| `1/1/1/1/8` | 12 | $538,781 | $0 | 4.27 | $448,984 | 0.00 | 35% | flat early; fat runner |
| `2/4/5/7/8` | 26 | $1,158,792 | $0 | 7.46 | $445,689 | 0.00 | 43% | rounded board contrib shares @ total=26 (runner≥8) |
| `2/3/4/5/8` | 22 | $972,671 | $0 | 7.38 | $442,123 | 0.00 | 42% | contrib ratios scaled up; runner=8 |
| `2/2/2/2/8` | 16 | $692,744 | $0 | 5.49 | $432,965 | 0.00 | 40% | same early as baseline; fat runner |
| `2/2/2/2/2` | 10 | $404,130 | $0 | 7.99 | $404,130 | 0.00 | 49% | control equal ladder |

### NAS100

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `1/1/2/2/12` | 18 | $127,373 | $0 | 5.42 | $70,763 | 0.00 | 35% | runner=12 |
| `1/1/1/2/10` | 15 | $106,081 | $0 | 5.35 | $70,721 | 0.00 | 36% | runner=10 |
| `1/1/1/1/8` | 12 | $83,755 | $0 | 5.59 | $69,795 | 0.00 | 36% | flat early; fat runner |
| `0/0/2/4/8` | 14 | $93,497 | $0 | 4.62 | $66,783 | 0.00 | 33% | only +6/+8 + runner |
| `0/1/2/3/8` | 14 | $91,426 | $0 | 4.91 | $65,305 | 0.00 | 33% | drop weakest contrib (tp1) |
| `1/1/2/2/8` | 14 | $88,978 | $0 | 5.23 | $63,556 | 0.00 | 36% | mild back-load; runner=8 |
| `1/2/2/3/10` | 18 | $112,365 | $0 | 5.14 | $62,425 | 0.00 | 35% | contrib-shaped; runner=10 |
| `0/1/3/4/8` | 16 | $96,650 | $0 | 4.68 | $60,406 | 0.00 | 33% | rounded board contrib shares @ total=16 (runner≥8) |
| `1/2/2/3/8` | 16 | $93,167 | $0 | 5.00 | $58,230 | 0.00 | 35% | contrib-shaped among scales; runner=8 (~share-weighted) |
| `2/2/2/2/8` | 16 | $90,719 | $0 | 5.34 | $56,700 | 0.00 | 38% | same early as baseline; fat runner |
| `1/2/3/4/8` | 18 | $98,391 | $0 | 4.77 | $54,662 | 0.00 | 35% | steeper back-weight + runner=8 |
| `0/3/4/5/8` | 20 | $103,993 | $0 | 4.59 | $51,997 | 0.00 | 33% | rounded board contrib shares @ total=20 (runner≥8) |
| `2/3/4/5/8` | 22 | $105,356 | $0 | 4.65 | $47,889 | 0.00 | 36% | contrib ratios scaled up; runner=8 |
| `2/4/5/7/8` | 26 | $114,769 | $0 | 4.36 | $44,142 | 0.00 | 36% | rounded board contrib shares @ total=26 (runner≥8) |
| `2/2/2/2/2` | 10 | $33,127 | $0 | 4.43 | $33,127 | 0.00 | 40% | control equal ladder |

### NQ

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `0/0/2/4/8` | 14 | $517,957 | $0 | 1.45 | $369,969 | 0.00 | 36% | only +6/+8 + runner |
| `0/1/3/4/8` | 16 | $580,427 | $0 | 1.58 | $362,767 | 0.00 | 38% | rounded board contrib shares @ total=16 (runner≥8) |
| `0/3/4/5/8` | 20 | $719,975 | $0 | 1.86 | $359,987 | 0.00 | 40% | rounded board contrib shares @ total=20 (runner≥8) |
| `0/1/2/3/8` | 14 | $488,743 | $0 | 1.37 | $349,102 | 0.00 | 36% | drop weakest contrib (tp1) |
| `2/4/5/7/8` | 26 | $907,391 | $0 | 2.18 | $348,997 | 0.00 | 42% | rounded board contrib shares @ total=26 (runner≥8) |
| `1/2/3/4/8` | 18 | $613,687 | $0 | 1.63 | $340,937 | 0.00 | 39% | steeper back-weight + runner=8 |
| `2/3/4/5/8` | 22 | $738,631 | $0 | 1.86 | $335,741 | 0.00 | 41% | contrib ratios scaled up; runner=8 |
| `1/2/2/3/8` | 16 | $522,003 | $0 | 1.42 | $326,252 | 0.00 | 38% | contrib-shaped among scales; runner=8 (~share-weighted) |
| `1/2/2/3/10` | 18 | $579,078 | $0 | 1.29 | $321,710 | 0.00 | 36% | contrib-shaped; runner=10 |
| `1/1/2/2/8` | 14 | $444,926 | $0 | 1.25 | $317,804 | 0.00 | 36% | mild back-load; runner=8 |
| `1/1/2/2/12` | 18 | $559,075 | $0 | 1.07 | $310,597 | 0.00 | 33% | runner=12 |
| `1/1/1/2/10` | 15 | $463,462 | $0 | 1.07 | $308,975 | 0.00 | 33% | runner=10 |
| `2/2/2/2/2` | 10 | $306,962 | $0 | 2.53 | $306,962 | 0.00 | 45% | control equal ladder |
| `2/2/2/2/8` | 16 | $478,186 | $0 | 1.30 | $298,866 | 0.00 | 38% | same early as baseline; fat runner |
| `1/1/1/1/8` | 12 | $353,242 | $0 | 1.02 | $294,369 | 0.00 | 33% | flat early; fat runner |

### EURUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `1/1/2/2/12` | 18 | $279,854 | $0 | 2.34 | $155,474 | 0.00 | 28% | runner=12 |
| `1/1/1/2/10` | 15 | $233,179 | $0 | 2.35 | $155,453 | 0.00 | 29% | runner=10 |
| `1/1/1/1/8` | 12 | $183,738 | $0 | 2.33 | $153,115 | 0.00 | 29% | flat early; fat runner |
| `0/0/2/4/8` | 14 | $210,300 | $0 | 2.42 | $150,214 | 0.00 | 28% | only +6/+8 + runner |
| `0/1/2/3/8` | 14 | $205,382 | $0 | 2.36 | $146,701 | 0.00 | 28% | drop weakest contrib (tp1) |
| `1/1/2/2/8` | 14 | $199,040 | $0 | 2.36 | $142,171 | 0.00 | 29% | mild back-load; runner=8 |
| `1/2/2/3/10` | 18 | $252,597 | $0 | 2.35 | $140,332 | 0.00 | 30% | contrib-shaped; runner=10 |
| `0/1/3/4/8` | 16 | $220,683 | $0 | 2.39 | $137,927 | 0.00 | 29% | rounded board contrib shares @ total=16 (runner≥8) |
| `1/2/2/3/8` | 16 | $212,190 | $0 | 2.36 | $132,619 | 0.00 | 30% | contrib-shaped among scales; runner=8 (~share-weighted) |
| `2/2/2/2/8` | 16 | $205,848 | $0 | 2.35 | $128,655 | 0.00 | 31% | same early as baseline; fat runner |
| `1/2/3/4/8` | 18 | $227,492 | $0 | 2.38 | $126,384 | 0.00 | 30% | steeper back-weight + runner=8 |
| `0/3/4/5/8` | 20 | $244,217 | $0 | 2.36 | $122,109 | 0.00 | 30% | rounded board contrib shares @ total=20 (runner≥8) |
| `2/3/4/5/8` | 22 | $249,601 | $0 | 2.40 | $113,455 | 0.00 | 32% | contrib ratios scaled up; runner=8 |
| `2/4/5/7/8` | 26 | $278,053 | $0 | 2.42 | $106,944 | 0.00 | 32% | rounded board contrib shares @ total=26 (runner≥8) |
| `2/2/2/2/2` | 10 | $84,627 | $0 | 2.44 | $84,627 | 0.00 | 35% | control equal ladder |

### XAUUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `1/1/1/2/10` | 15 | $650,697 | $0 | 3.10 | $433,798 | 0.00 | 35% | runner=10 |
| `1/1/2/2/12` | 18 | $779,704 | $0 | 3.10 | $433,169 | 0.00 | 34% | runner=12 |
| `1/1/1/1/8` | 12 | $511,781 | $0 | 3.05 | $426,484 | 0.00 | 35% | flat early; fat runner |
| `0/0/2/4/8` | 14 | $592,960 | $0 | 3.54 | $423,543 | 0.00 | 33% | only +6/+8 + runner |
| `0/1/2/3/8` | 14 | $582,055 | $0 | 3.47 | $415,754 | 0.00 | 34% | drop weakest contrib (tp1) |
| `1/1/2/2/8` | 14 | $558,987 | $0 | 3.33 | $399,277 | 0.00 | 36% | mild back-load; runner=8 |
| `1/2/2/3/10` | 18 | $715,556 | $0 | 3.41 | $397,531 | 0.00 | 36% | contrib-shaped; runner=10 |
| `0/1/3/4/8` | 16 | $629,261 | $0 | 3.75 | $393,288 | 0.00 | 35% | rounded board contrib shares @ total=16 (runner≥8) |
| `1/2/2/3/8` | 16 | $605,197 | $0 | 3.61 | $378,248 | 0.00 | 37% | contrib-shaped among scales; runner=8 (~share-weighted) |
| `2/2/2/2/8` | 16 | $582,129 | $0 | 3.47 | $363,831 | 0.00 | 38% | same early as baseline; fat runner |
| `1/2/3/4/8` | 18 | $652,403 | $0 | 3.89 | $362,446 | 0.00 | 37% | steeper back-weight + runner=8 |
| `0/3/4/5/8` | 20 | $711,773 | $0 | 4.24 | $355,886 | 0.00 | 37% | rounded board contrib shares @ total=20 (runner≥8) |
| `2/3/4/5/8` | 22 | $722,751 | $0 | 4.31 | $328,523 | 0.00 | 38% | contrib ratios scaled up; runner=8 |
| `2/4/5/7/8` | 26 | $816,167 | $0 | 4.42 | $313,910 | 0.00 | 39% | rounded board contrib shares @ total=26 (runner≥8) |
| `2/2/2/2/2` | 10 | $251,054 | $0 | 4.08 | $251,054 | 0.00 | 43% | control equal ladder |

## Board aggregate (sum net/10ct; worst stress/10ct)

| sizing | Σ net/10ct | Σ stress/10ct | N/Sₙ | note |
|---|---:|---:|---:|---|
| `0/0/2/4/8` | $1,494,079 | $0 | 0.00 | only +6/+8 + runner |
| `0/1/2/3/8` | $1,451,680 | $0 | 0.00 | drop weakest contrib (tp1) |
| `0/1/3/4/8` | $1,428,484 | $0 | 0.00 | rounded board contrib shares @ total=16 (runner≥8) |
| `1/1/2/2/12` | $1,428,335 | $0 | 0.00 | runner=12 |
| `1/1/1/2/10` | $1,427,125 | $0 | 0.00 | runner=10 |
| `1/1/1/1/8` | $1,392,748 | $0 | 0.00 | flat early; fat runner |
| `1/2/2/3/10` | $1,378,168 | $0 | 0.00 | contrib-shaped; runner=10 |
| `1/1/2/2/8` | $1,374,656 | $0 | 0.00 | mild back-load; runner=8 |
| `0/3/4/5/8` | $1,356,190 | $0 | 0.00 | rounded board contrib shares @ total=20 (runner≥8) |
| `1/2/2/3/8` | $1,348,412 | $0 | 0.00 | contrib-shaped among scales; runner=8 (~share-weighted) |
| `1/2/3/4/8` | $1,339,268 | $0 | 0.00 | steeper back-weight + runner=8 |
| `2/2/2/2/8` | $1,281,016 | $0 | 0.00 | same early as baseline; fat runner |
| `2/3/4/5/8` | $1,267,732 | $0 | 0.00 | contrib ratios scaled up; runner=8 |
| `2/4/5/7/8` | $1,259,682 | $0 | 0.00 | rounded board contrib shares @ total=26 (runner≥8) |
| `2/2/2/2/2` | $1,079,900 | $0 | 0.00 | control equal ladder |

Hub: `live/state/quarterly_atr4_ladder_sizing_sweep`
