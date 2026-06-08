# NQ Prior-Opposed v2b Filter Study

This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.

Reduced-size scenarios are unit-level by campaign unit rank, not proportional approximations:

- `1_1_3`: original five-unit `S_1_1_3` campaign.
- `1_1_1`: keep the first three units in each campaign, dropping two runner units.
- `1_1_0`: keep the first two units in each campaign, dropping all runner units.

Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.

## Scenario Matrix

| scenario              |   trades |    net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:----------------------|---------:|-----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| or_q4_high_to_1_1_1   |      352 | 1137539.00 |       -35274.50 |       -37867.00 |             30.04 |          69.60 |            3.10 |     3231.64 |
| or_q4_high_to_1_1_0   |      352 | 1114016.00 |       -35718.00 |       -38310.50 |             29.08 |          70.45 |            3.34 |     3164.82 |
| or_or_gap_q4_to_1_1_1 |      352 | 1078064.00 |       -35274.50 |       -37867.00 |             28.47 |          69.89 |            3.11 |     3062.68 |
| gap_q4_high_to_1_1_0  |      352 | 1101599.00 |       -34652.50 |       -38943.00 |             28.29 |          70.45 |            3.08 |     3129.54 |
| skip_gap_q4_high      |      280 | 1039015.00 |       -34652.50 |       -37765.00 |             27.51 |          71.79 |            3.37 |     3710.77 |
| gap_q4_high_to_1_1_1  |      352 | 1129261.00 |       -34652.50 |       -41384.50 |             27.29 |          69.89 |            2.96 |     3208.13 |
| skip_or_q4_high       |      264 | 1021175.00 |       -36605.00 |       -39197.50 |             26.05 |          71.59 |            3.89 |     3868.09 |
| base_1_1_3            |      352 | 1184585.00 |       -34652.50 |       -46267.50 |             25.60 |          69.32 |            2.75 |     3365.30 |
| skip_2022_or_or_q4    |      258 |  998015.00 |       -36605.00 |       -39197.50 |             25.46 |          71.71 |            4.01 |     3868.28 |
| skip_2022             |      336 | 1171160.00 |       -34652.50 |       -46267.50 |             25.31 |          69.94 |            2.96 |     3485.60 |
| skip_or_q4_or_gap_q4  |      229 |  887562.50 |       -36605.00 |       -39197.50 |             22.64 |          72.05 |            4.12 |     3875.82 |
| delete_top_5_winners  |      347 |  988567.50 |       -37012.50 |       -46267.50 |             21.37 |          68.88 |            2.46 |     2848.90 |
| delete_top_10_winners |      342 |  852235.00 |       -37012.50 |       -46267.50 |             18.42 |          68.42 |            2.26 |     2491.92 |
| delete_top_20_winners |      332 |  642395.00 |       -54792.50 |       -61017.50 |             10.53 |          67.47 |            1.95 |     1934.92 |

## Read

- The best Net/Stress row in this filter pass is **or_q4_high_to_1_1_1** at 30.04 Net/Stress, versus base 25.60.
- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.
- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.

## 2022 Forensics

2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).

## Files

- `filter_scenario_matrix.csv`
- `campaigns_with_sizing.csv`
- `campaigns_2022.csv`
