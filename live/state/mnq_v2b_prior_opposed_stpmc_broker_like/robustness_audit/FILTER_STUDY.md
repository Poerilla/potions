# MNQ Prior-Opposed v2b Filter Study

This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.

Reduced-size scenarios are unit-level, not proportional approximations:

- `1_1_3`: original five-unit `S_1_1_3` campaign.
- `1_1_1`: keep unit IDs 1-3, dropping two runner units.
- `1_1_0`: keep unit IDs 1-2, dropping all runner units.

Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.

## Scenario Matrix

| scenario              |   trades |   net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:----------------------|---------:|----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| or_q4_high_to_1_1_1   |      353 | 109077.50 |        -3573.50 |        -3831.00 |             28.47 |          68.84 |            2.93 |      309.00 |
| or_or_gap_q4_to_1_1_1 |      353 | 109077.50 |        -3573.50 |        -3831.00 |             28.47 |          68.84 |            2.93 |      309.00 |
| or_q4_high_to_1_1_0   |      353 | 106842.50 |        -3618.00 |        -3875.50 |             27.57 |          69.69 |            3.14 |      302.67 |
| skip_or_q4_high       |      265 |  97766.00 |        -3707.00 |        -3964.50 |             24.66 |          70.57 |            3.60 |      368.93 |
| skip_or_q4_or_gap_q4  |      265 |  97766.00 |        -3707.00 |        -3964.50 |             24.66 |          70.57 |            3.60 |      368.93 |
| base_1_1_3            |      353 | 113547.50 |        -3493.50 |        -4654.50 |             24.40 |          68.56 |            2.61 |      321.66 |
| skip_gap_q4_high      |      353 | 113547.50 |        -3493.50 |        -4654.50 |             24.40 |          68.56 |            2.61 |      321.66 |
| gap_q4_high_to_1_1_1  |      353 | 113547.50 |        -3493.50 |        -4654.50 |             24.40 |          68.56 |            2.61 |      321.66 |
| gap_q4_high_to_1_1_0  |      353 | 113547.50 |        -3493.50 |        -4654.50 |             24.40 |          68.56 |            2.61 |      321.66 |
| skip_2022             |      337 | 112673.00 |        -3493.50 |        -4654.50 |             24.21 |          69.14 |            2.81 |      334.34 |
| skip_2022_or_or_q4    |      259 |  95879.50 |        -3707.00 |        -3964.50 |             24.18 |          70.66 |            3.70 |      370.19 |
| delete_top_5_winners  |      348 |  93987.00 |        -3493.50 |        -4654.50 |             20.19 |          68.10 |            2.34 |      270.08 |
| delete_top_10_winners |      343 |  80381.50 |        -3498.00 |        -4690.50 |             17.14 |          67.64 |            2.14 |      234.35 |
| delete_top_20_winners |      333 |  59388.00 |        -5629.00 |        -6246.50 |              9.51 |          66.67 |            1.84 |      178.34 |

## Read

- The best Net/Stress row in this filter pass is **or_q4_high_to_1_1_1** at 28.47 Net/Stress, versus base 24.40.
- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.
- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.

## 2022 Forensics

2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Files

- `filter_scenario_matrix.csv`
- `campaigns_with_sizing.csv`
- `campaigns_2022.csv`