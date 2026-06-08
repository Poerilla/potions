# MNQ yearly ORB — $20k half-profit-linked scaling

Variant: yearly ORB scaleout3, inside-range swing stop, range-close exit (same CSV as equity scaling).
**R** = 3 × |full-sample open-heat stress DD| one bundle = **$13,812**.

## Sizing rule

- At each **1 Jan**: `bundles = floor(min(equity, sizing_budget) / (R × buffer))`, cap 250 bundles.
- **Equity** compounds full realized P&L at that year’s bundle count.
- **Sizing budget** is updated after each year from the regime’s profit rule (capped by equity).

### Regimes

| Track | Profit → sizing budget | Buffer × R | Loss handling |
|---|---|---|---|
| Aggressive | 50% of year net **+** 50% of mean 1-bundle year every year; extra 0.5× mean on loss years | 1.00 | sizes off profit *and* expected |
| Moderate | 50% of year net | 1.10 | losses do not add to sizing budget |
| Conservative | 50% of year net on gains; losses shrink sizing budget by 25% of loss | 1.33 | asymmetric |

**Mean 1-bundle calendar-year net** (2020–2025): **$11,347** (sample σ ≈ **$3,726**).

## A) Historical tape: **$20,000** start **2020**

### Aggressive

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net |   year_closed_dd |   year_stress_dd |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|-----------------:|-----------------:|-------------:|--------------------:|
|   2020 |        20000   |               20000   |         1 |           3 |              13812 |    13574.1 |           -505.5 |          -1576.5 |      33574.1 |             32460.5 |
|   2021 |        33574.1 |               32460.5 |         2 |           6 |              13812 |    14513.2 |          -3684   |          -5277   |      48087.4 |             45390.6 |
|   2022 |        48087.4 |               45390.6 |         3 |           9 |              13812 |    22130.2 |          -9469.5 |         -13812   |      70217.6 |             62129.2 |
|   2023 |        70217.6 |               62129.2 |         4 |          12 |              13812 |    54179   |           -966   |          -2460   |     124397   |             94892.2 |
|   2024 |       124397   |               94892.2 |         6 |          18 |              13812 |    59768.2 |          -7944   |         -16854   |     184165   |            130450   |
|   2025 |       184165   |              130450   |         9 |          27 |              13812 |   147312   |         -15687   |         -32220   |     331477   |            209779   |

### Moderate

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net |   year_closed_dd |   year_stress_dd |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|-----------------:|-----------------:|-------------:|--------------------:|
|   2020 |        20000   |               20000   |         1 |           3 |            15193.2 |   13574.1  |           -505.5 |          -1576.5 |      33574.1 |             26787.1 |
|   2021 |        33574.1 |               26787.1 |         1 |           3 |            15193.2 |    7256.62 |          -1842   |          -2638.5 |      40830.8 |             30415.4 |
|   2022 |        40830.8 |               30415.4 |         2 |           6 |            15193.2 |   14753.5  |          -6313   |          -9208   |      55584.2 |             37792.1 |
|   2023 |        55584.2 |               37792.1 |         2 |           6 |            15193.2 |   27089.5  |           -483   |          -1230   |      82673.8 |             51336.9 |
|   2024 |        82673.8 |               51336.9 |         3 |           9 |            15193.2 |   29884.1  |          -3972   |          -8427   |     112558   |             66278.9 |
|   2025 |       112558   |               66278.9 |         4 |          12 |            15193.2 |   65472    |          -6972   |         -14320   |     178030   |             99014.9 |

### Conservative

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net |   year_closed_dd |   year_stress_dd |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|-----------------:|-----------------:|-------------:|--------------------:|
|   2020 |        20000   |               20000   |         1 |           3 |              18370 |   13574.1  |           -505.5 |          -1576.5 |      33574.1 |             26787.1 |
|   2021 |        33574.1 |               26787.1 |         1 |           3 |              18370 |    7256.62 |          -1842   |          -2638.5 |      40830.8 |             30415.4 |
|   2022 |        40830.8 |               30415.4 |         1 |           3 |              18370 |    7376.75 |          -3156.5 |          -4604   |      48207.5 |             34103.8 |
|   2023 |        48207.5 |               34103.8 |         1 |           3 |              18370 |   13544.8  |           -241.5 |           -615   |      61752.2 |             40876.1 |
|   2024 |        61752.2 |               40876.1 |         2 |           6 |              18370 |   19922.8  |          -2648   |          -5618   |      81675   |             50837.5 |
|   2025 |        81675   |               50837.5 |         2 |           6 |              18370 |   32736    |          -3486   |          -7160   |     114411   |             67205.5 |

## B) Synthetic forward: **$20,000** on **2026-01-01** (5 years)

No post-2025 trades in the CSV. Each year uses **deterministic** P&L = mean historical
1-bundle year net ($11,347) × bundle count. Stress/closed DD not extrapolated.

### Aggressive (2026–2030)

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net | year_closed_dd   | year_stress_dd   |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|:-----------------|:-----------------|-------------:|--------------------:|
|   2026 |        20000   |               20000   |         1 |           3 |              13812 |    11346.9 |                  |                  |      31346.9 |             31346.9 |
|   2027 |        31346.9 |               31346.9 |         2 |           6 |              13812 |    22693.9 |                  |                  |      54040.8 |             48367.3 |
|   2028 |        54040.8 |               48367.3 |         3 |           9 |              13812 |    34040.8 |                  |                  |      88081.6 |             71061.2 |
|   2029 |        88081.6 |               71061.2 |         5 |          15 |              13812 |    56734.7 |                  |                  |     144816   |            105102   |
|   2030 |       144816   |              105102   |         7 |          21 |              13812 |    79428.6 |                  |                  |     224245   |            150490   |

_synthetic year P&L = 11347 * bundles (hist σ 1-bundle ≈ 3726)_

### Moderate (2026–2030)

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net | year_closed_dd   | year_stress_dd   |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|:-----------------|:-----------------|-------------:|--------------------:|
|   2026 |        20000   |               20000   |         1 |           3 |            15193.2 |    11346.9 |                  |                  |      31346.9 |             25673.5 |
|   2027 |        31346.9 |               25673.5 |         1 |           3 |            15193.2 |    11346.9 |                  |                  |      42693.9 |             31346.9 |
|   2028 |        42693.9 |               31346.9 |         2 |           6 |            15193.2 |    22693.9 |                  |                  |      65387.8 |             42693.9 |
|   2029 |        65387.8 |               42693.9 |         2 |           6 |            15193.2 |    22693.9 |                  |                  |      88081.6 |             54040.8 |
|   2030 |        88081.6 |               54040.8 |         3 |           9 |            15193.2 |    34040.8 |                  |                  |     122122   |             71061.2 |

_synthetic year P&L = 11347 * bundles (hist σ 1-bundle ≈ 3726)_

### Conservative (2026–2030)

|   year |   start_equity |   sizing_budget_start |   bundles |   contracts |   eff_r_per_bundle |   year_net | year_closed_dd   | year_stress_dd   |   end_equity |   sizing_budget_end |
|-------:|---------------:|----------------------:|----------:|------------:|-------------------:|-----------:|:-----------------|:-----------------|-------------:|--------------------:|
|   2026 |        20000   |               20000   |         1 |           3 |              18370 |    11346.9 |                  |                  |      31346.9 |             25673.5 |
|   2027 |        31346.9 |               25673.5 |         1 |           3 |              18370 |    11346.9 |                  |                  |      42693.9 |             31346.9 |
|   2028 |        42693.9 |               31346.9 |         1 |           3 |              18370 |    11346.9 |                  |                  |      54040.8 |             37020.4 |
|   2029 |        54040.8 |               37020.4 |         2 |           6 |              18370 |    22693.9 |                  |                  |      76734.7 |             48367.3 |
|   2030 |        76734.7 |               48367.3 |         2 |           6 |              18370 |    22693.9 |                  |                  |      99428.6 |             59714.3 |

_synthetic year P&L = 11347 * bundles (hist σ 1-bundle ≈ 3726)_
