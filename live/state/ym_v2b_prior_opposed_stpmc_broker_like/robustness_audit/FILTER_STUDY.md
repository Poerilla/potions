# YM Prior-Opposed v2b Filter Study

This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.

Reduced-size scenarios are unit-level, not proportional approximations:

- `1_1_3`: original five-unit `S_1_1_3` campaign.
- `1_1_1`: keep unit IDs 1-3, dropping two runner units.
- `1_1_0`: keep unit IDs 1-2, dropping all runner units.

Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.

## Scenario Matrix

| scenario              |   trades |   net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:----------------------|---------:|----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| base_1_1_3            |      347 | 320190.00 |       -24017.50 |       -24298.75 |             13.18 |          59.65 |            1.89 |      922.74 |
| skip_gap_q4_high      |      347 | 320190.00 |       -24017.50 |       -24298.75 |             13.18 |          59.65 |            1.89 |      922.74 |
| gap_q4_high_to_1_1_1  |      347 | 320190.00 |       -24017.50 |       -24298.75 |             13.18 |          59.65 |            1.89 |      922.74 |
| gap_q4_high_to_1_1_0  |      347 | 320190.00 |       -24017.50 |       -24298.75 |             13.18 |          59.65 |            1.89 |      922.74 |
| or_q4_high_to_1_1_1   |      347 | 278086.00 |       -20203.25 |       -21334.50 |             13.03 |          59.94 |            1.91 |      801.40 |
| or_or_gap_q4_to_1_1_1 |      347 | 278086.00 |       -20203.25 |       -21334.50 |             13.03 |          59.94 |            1.91 |      801.40 |
| or_q4_high_to_1_1_0   |      347 | 257034.00 |       -19230.50 |       -20361.75 |             12.62 |          60.23 |            1.93 |      740.73 |
| skip_or_q4_high       |      260 | 213651.25 |       -17285.00 |       -18416.25 |             11.60 |          59.62 |            1.95 |      821.74 |
| skip_or_q4_or_gap_q4  |      260 | 213651.25 |       -17285.00 |       -18416.25 |             11.60 |          59.62 |            1.95 |      821.74 |
| skip_2022             |      326 | 271005.00 |       -24017.50 |       -24298.75 |             11.15 |          58.90 |            1.80 |      831.30 |
| delete_top_5_winners  |      342 | 260162.50 |       -24017.50 |       -24298.75 |             10.71 |          59.06 |            1.72 |      760.71 |
| skip_2022_or_or_q4    |      246 | 180342.50 |       -17285.00 |       -18416.25 |              9.79 |          58.54 |            1.83 |      733.10 |
| delete_top_10_winners |      337 | 214800.00 |       -24017.50 |       -24298.75 |              8.84 |          58.46 |            1.60 |      637.39 |
| delete_top_20_winners |      327 | 139510.00 |       -25943.75 |       -26225.00 |              5.32 |          57.19 |            1.39 |      426.64 |

## Read

- The best Net/Stress row in this filter pass is **base_1_1_3** at 13.18 Net/Stress, versus base 13.18.
- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.
- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.

## 2022 Forensics

2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Files

- `filter_scenario_matrix.csv`
- `campaigns_with_sizing.csv`
- `campaigns_2022.csv`