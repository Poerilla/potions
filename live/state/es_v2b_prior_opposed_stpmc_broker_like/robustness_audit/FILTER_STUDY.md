# ES Prior-Opposed v2b Filter Study

This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.

Reduced-size scenarios are unit-level, not proportional approximations:

- `1_1_3`: original five-unit `S_1_1_3` campaign.
- `1_1_1`: keep unit IDs 1-3, dropping two runner units.
- `1_1_0`: keep unit IDs 1-2, dropping all runner units.

Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.

## Scenario Matrix

| scenario              |   trades |   net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:----------------------|---------:|----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| skip_2022_or_or_q4    |      179 | 242295.00 |       -16865.00 |       -17365.00 |             13.95 |          66.48 |            2.75 |     1353.60 |
| or_q4_high_to_1_1_0   |      245 | 284682.50 |       -19898.50 |       -21211.00 |             13.42 |          63.67 |            2.41 |     1161.97 |
| or_q4_high_to_1_1_1   |      245 | 306017.50 |       -21634.00 |       -22946.50 |             13.34 |          63.67 |            2.32 |     1249.05 |
| or_or_gap_q4_to_1_1_1 |      245 | 306017.50 |       -21634.00 |       -22946.50 |             13.34 |          63.67 |            2.32 |     1249.05 |
| base_1_1_3            |      245 | 348687.50 |       -27950.00 |       -29262.50 |             11.92 |          63.67 |            2.18 |     1423.21 |
| skip_gap_q4_high      |      245 | 348687.50 |       -27950.00 |       -29262.50 |             11.92 |          63.67 |            2.18 |     1423.21 |
| gap_q4_high_to_1_1_1  |      245 | 348687.50 |       -27950.00 |       -29262.50 |             11.92 |          63.67 |            2.18 |     1423.21 |
| gap_q4_high_to_1_1_0  |      245 | 348687.50 |       -27950.00 |       -29262.50 |             11.92 |          63.67 |            2.18 |     1423.21 |
| skip_or_q4_high       |      185 | 233062.50 |       -19597.50 |       -20910.00 |             11.15 |          65.41 |            2.55 |     1259.80 |
| skip_or_q4_or_gap_q4  |      185 | 233062.50 |       -19597.50 |       -20910.00 |             11.15 |          65.41 |            2.55 |     1259.80 |
| skip_2022             |      230 | 323400.00 |       -27950.00 |       -29262.50 |             11.05 |          64.35 |            2.23 |     1406.09 |
| delete_top_5_winners  |      240 | 264987.50 |       -32612.50 |       -33925.00 |              7.81 |          62.92 |            1.90 |     1104.11 |
| delete_top_10_winners |      235 | 206312.50 |       -32612.50 |       -33925.00 |              6.08 |          62.13 |            1.70 |      877.93 |
| delete_top_20_winners |      225 | 111137.50 |       -35157.50 |       -37907.50 |              2.93 |          60.44 |            1.38 |      493.94 |

## Read

- The best Net/Stress row in this filter pass is **skip_2022_or_or_q4** at 13.95 Net/Stress, versus base 11.92.
- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.
- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.

## 2022 Forensics

2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Files

- `filter_scenario_matrix.csv`
- `campaigns_with_sizing.csv`
- `campaigns_2022.csv`