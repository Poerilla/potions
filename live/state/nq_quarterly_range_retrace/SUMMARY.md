# NQ Quarterly Range Take → Retrace Study

When quarter **N+1** takes an extreme of quarter **N** (trades beyond prior high or prior low), measure how far price travels **back into** N's range during N+1 after the break (max fill toward the opposite extreme, capped at 100% of prior width for the % metric; `exceeded_opposite_extreme` flags a full traverse).

- Daily source: `/home/tester/hsm/potions/nq/nq_daily.csv`
- Quarters measured: **64** (2010Q2 → 2026Q1)
- Take events: **69** (18 take-low / 51 take-high)

## Aggregate retrace into prior range

### All takes

- N takes: **69**
- Median retrace into prior range: **29.7%**
- Mean retrace: **41.0%**
- P25 / P75: **12.6%** / **63.4%**
- Full-range fill (≥100% of prior width toward opposite extreme): **11** (15.9%)
- Exceeded opposite prior extreme: **11**

### Take prior low (then bounce back up into range)

- N takes: **18**
- Median retrace into prior range: **62.0%**
- Mean retrace: **63.2%**
- P25 / P75: **41.9%** / **100.0%**
- Full-range fill (≥100% of prior width toward opposite extreme): **6** (33.3%)
- Exceeded opposite prior extreme: **6**

### Take prior high (then pull back down into range)

- N takes: **51**
- Median retrace into prior range: **19.7%**
- Mean retrace: **33.1%**
- P25 / P75: **10.2%** / **44.4%**
- Full-range fill (≥100% of prior width toward opposite extreme): **5** (9.8%)
- Exceeded opposite prior extreme: **5**

### By next-quarter seasonality

| Next Q | Side | N | Median % | Mean % | ≥100% |
|---:|---|---:|---:|---:|---:|
| Q1 | take_low | 4 | 38.7 | 42.1 | 0 |
| Q1 | take_high | 10 | 24.2 | 31.5 | 1 |
| Q2 | take_low | 4 | 81.7 | 70.3 | 2 |
| Q2 | take_high | 13 | 24.6 | 37.6 | 1 |
| Q3 | take_low | 4 | 62.0 | 57.8 | 1 |
| Q3 | take_high | 15 | 13.6 | 34.2 | 2 |
| Q4 | take_low | 6 | 77.8 | 76.3 | 3 |
| Q4 | take_high | 13 | 17.2 | 28.7 | 1 |

## Charts

One daily-candle chart per calendar year. Prior-quarter high (dashed) and low (solid) horizontals are drawn across the **next quarter only**. Markers: triangle = break of prior extreme; diamond = deepest retrace into prior range.

| Year | Chart | Takes in year (as next-Q) |
|---:|---|---:|
| 2010 | [charts/2010.png](charts/2010.png) | 3 |
| 2011 | [charts/2011.png](charts/2011.png) | 5 |
| 2012 | [charts/2012.png](charts/2012.png) | 4 |
| 2013 | [charts/2013.png](charts/2013.png) | 3 |
| 2014 | [charts/2014.png](charts/2014.png) | 6 |
| 2015 | [charts/2015.png](charts/2015.png) | 5 |
| 2016 | [charts/2016.png](charts/2016.png) | 3 |
| 2017 | [charts/2017.png](charts/2017.png) | 4 |
| 2018 | [charts/2018.png](charts/2018.png) | 5 |
| 2019 | [charts/2019.png](charts/2019.png) | 3 |
| 2020 | [charts/2020.png](charts/2020.png) | 5 |
| 2021 | [charts/2021.png](charts/2021.png) | 5 |
| 2022 | [charts/2022.png](charts/2022.png) | 4 |
| 2023 | [charts/2023.png](charts/2023.png) | 5 |
| 2024 | [charts/2024.png](charts/2024.png) | 4 |
| 2025 | [charts/2025.png](charts/2025.png) | 5 |
| 2026 | [charts/2026.png](charts/2026.png) | 0 |

## Files

- `quarters.csv` — every quarter high/low
- `takes.csv` — every next-quarter take + retrace metrics
- `charts/` — yearly daily PNGs
