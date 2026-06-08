# MYM Prior-Opposed v2b Filter Study

This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.

Reduced-size scenarios are unit-level, not proportional approximations:

- `1_1_3`: original five-unit `S_1_1_3` campaign.
- `1_1_1`: keep unit IDs 1-3, dropping two runner units.
- `1_1_0`: keep unit IDs 1-2, dropping all runner units.

Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.

## Scenario Matrix

| scenario              |   trades |   net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:----------------------|---------:|----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| or_q4_high_to_1_1_1   |      333 |  22530.28 |        -1819.08 |        -2022.87 |             11.14 |          59.76 |            1.75 |       67.66 |
| or_or_gap_q4_to_1_1_1 |      333 |  22530.28 |        -1819.08 |        -2022.87 |             11.14 |          59.76 |            1.75 |       67.66 |
| or_q4_high_to_1_1_0   |      333 |  20766.36 |        -1720.46 |        -1924.25 |             10.79 |          60.36 |            1.76 |       62.36 |
| base_1_1_3            |      333 |  26058.12 |        -2481.96 |        -2558.71 |             10.18 |          59.76 |            1.74 |       78.25 |
| skip_gap_q4_high      |      333 |  26058.12 |        -2481.96 |        -2558.71 |             10.18 |          59.76 |            1.74 |       78.25 |
| gap_q4_high_to_1_1_1  |      333 |  26058.12 |        -2481.96 |        -2558.71 |             10.18 |          59.76 |            1.74 |       78.25 |
| gap_q4_high_to_1_1_0  |      333 |  26058.12 |        -2481.96 |        -2558.71 |             10.18 |          59.76 |            1.74 |       78.25 |
| skip_or_q4_high       |      250 |  16919.12 |        -1593.00 |        -1727.01 |              9.80 |          59.20 |            1.74 |       67.68 |
| skip_or_q4_or_gap_q4  |      250 |  16919.12 |        -1593.00 |        -1727.01 |              9.80 |          59.20 |            1.74 |       67.68 |
| skip_2022             |      312 |  21263.12 |        -2481.96 |        -2558.71 |              8.31 |          58.97 |            1.65 |       68.15 |
| delete_top_5_winners  |      328 |  20543.52 |        -2481.96 |        -2558.71 |              8.03 |          59.15 |            1.59 |       62.63 |
| skip_2022_or_or_q4    |      236 |  13675.12 |        -1593.00 |        -1727.01 |              7.92 |          58.05 |            1.62 |       57.95 |
| delete_top_10_winners |      323 |  16245.82 |        -2481.96 |        -2558.71 |              6.35 |          58.51 |            1.46 |       50.30 |
| delete_top_20_winners |      313 |   9123.52 |        -3321.62 |        -3768.62 |              2.42 |          57.19 |            1.26 |       29.15 |

## Read

- The best Net/Stress row in this filter pass is **or_q4_high_to_1_1_1** at 11.14 Net/Stress, versus base 10.18.
- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.
- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.

## 2022 Forensics

2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Files

- `filter_scenario_matrix.csv`
- `campaigns_with_sizing.csv`
- `campaigns_2022.csv`