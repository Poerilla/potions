# Monday OR breakout — 1h HTF loser clusters

Primary trades joined to last completed 1h bar at entry. OBV SMA = 20.
Sample: **2092** trades with valid MA/OBV (of 2093 primary).

## Summary

- Flat@50% (failed breaks): **1371**
- Of flat@50%: MA **opposed** 625 (46%), OBV **opposed** 208 (15%)
- Flat@50% with **both** MA+OBV opposed: **88** (6%) net $-76,508
- Flat@50% with **both** aligned: **626** (46%) net $-558,614

### MA50 vs MA150 regime (aligned = trade with MA50>MA150 for longs)

| Bucket | n | Wins | Losses | Flat@50 | WR | Net |
|---|---:|---:|---:|---:|---:|---:|
| aligned | 1163 | 332 | 831 | 746 | 28.5% | $67,741 |
| opposed | 929 | 249 | 680 | 625 | 26.8% | $36,067 |

### OBV vs OBV-SMA20 regime

| Bucket | n | Wins | Losses | Flat@50 | WR | Net |
|---|---:|---:|---:|---:|---:|---:|
| aligned | 1802 | 514 | 1288 | 1163 | 28.5% | $109,575 |
| opposed | 290 | 67 | 223 | 208 | 23.1% | $-5,767 |

### MA × OBV combo

| MA | OBV | n | Flat@50 | WR | Net |
|---|---|---:|---:|---:|---:|
| aligned | aligned | 993 | 626 | 29.1% | $45,601 |
| aligned | opposed | 170 | 120 | 25.3% | $22,140 |
| opposed | aligned | 809 | 537 | 27.8% | $63,974 |
| opposed | opposed | 120 | 88 | 20.0% | $-27,907 |

### Fresh 1h MA50/150 cross opposed to trade

- Yes: n=5 flat50=3 WR=40.0% net=$2,568
- No:  n=2087 flat50=1368 WR=27.7% net=$101,240

### Fresh 1h OBV×SMA20 cross opposed to trade

- Yes: n=46 flat50=36 WR=8.7% net=$-33,249
- No:  n=2046 flat50=1335 WR=28.2% net=$137,057

## Hypothetical filter: skip MA-opposed entries

- Keep aligned: n=1163 net=$67,741 WR=28.5% flat50=746
- Skip opposed: n=929 net=$36,067 WR=26.8% flat50=625

## Hypothetical filter: skip OBV-opposed entries

- Keep aligned: n=1802 net=$109,575 WR=28.5% flat50=1163
- Skip opposed: n=290 net=$-5,767 WR=23.1% flat50=208

## Hypothetical: skip when BOTH MA and OBV opposed

- Skip both-opposed: n=120 net=$-27,907 flat50=88
- Keep rest: n=1972 net=$131,715 WR=28.2% flat50=1283
