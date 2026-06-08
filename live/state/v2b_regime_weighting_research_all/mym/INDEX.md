# MYM v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: MYM unit trades from `/home/tester/hsm/potions/live/state/v2b_sizing_sweep/states/mym_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session MYM hourly ST+PMC `mym_hourly_st_pmc_base_1x_50sl_150tp`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 1374 | 52.04 | -5027.66 | -24343.03 | -0.21 | 0.974 | -3.66 | -224.84 | 10 | 48686.05 | -0.0201 |
| B_hard_filter_not_aligned_1_1_3 | 1219 | 51.19 | -9093.82 | -23242.69 | -0.39 | 0.949 | -7.46 | -227.70 | 12 | 58106.71 | -0.0203 |
| C_weight_not_aligned_2_1_3 | 1374 | 52.33 | -5999.78 | -28160.57 | -0.21 | 0.974 | -4.37 | -265.24 | 10 | 64769.31 | -0.0139 |
| D_weight_not_aligned_2_2_3 | 1374 | 52.33 | -7012.20 | -32433.48 | -0.22 | 0.974 | -5.10 | -305.65 | 10 | 74596.99 | -0.0141 |
| E_weight_not_aligned_3_2_3 | 1374 | 52.40 | -8110.56 | -36465.52 | -0.22 | 0.973 | -5.90 | -346.05 | 10 | 83870.70 | -0.0145 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 1374 | 52.55 | -7404.46 | -27585.45 | -0.27 | 0.967 | -5.39 | -256.11 | 10 | 63446.53 | -0.0175 |
| G_skip_aligned_not_2_2_3 | 1219 | 51.52 | -11078.36 | -31267.14 | -0.35 | 0.955 | -9.09 | -318.78 | 12 | 78167.84 | -0.0184 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 155 | 58.71 | 4066.16 | -2625.12 | 1.55 | 1.218 | 26.23 | -202.34 |
| A_base_all_1_1_3 | not_aligned | 1219 | 51.19 | -9093.82 | -23242.69 | -0.39 | 0.949 | -7.46 | -227.70 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 208 | 58.17 | 9632.24 | -3348.11 | 2.88 | 1.347 | 46.31 | -218.92 |
| A_base_all_1_1_3 | not_aligned_no_prior | 1011 | 49.75 | -18726.06 | -24177.64 | -0.77 | 0.875 | -18.52 | -229.51 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 1219 | 51.19 | -9093.82 | -23242.69 | -0.39 | 0.949 | -7.46 | -227.70 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 208 | 58.17 | 9632.24 | -3348.11 | 2.88 | 1.347 | 46.31 | -218.92 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 1011 | 49.75 | -18726.06 | -24177.64 | -0.77 | 0.875 | -18.52 | -229.51 |
| C_weight_not_aligned_2_1_3 | aligned | 155 | 58.71 | 4066.16 | -2625.12 | 1.55 | 1.218 | 26.23 | -202.34 |
| C_weight_not_aligned_2_1_3 | not_aligned | 1219 | 51.52 | -10065.94 | -26994.23 | -0.37 | 0.953 | -8.26 | -273.24 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 208 | 58.65 | 11404.14 | -4077.47 | 2.80 | 1.342 | 54.83 | -262.70 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 1011 | 50.05 | -21470.08 | -27741.11 | -0.77 | 0.880 | -21.24 | -275.41 |
| D_weight_not_aligned_2_2_3 | aligned | 155 | 58.71 | 4066.16 | -2625.12 | 1.55 | 1.218 | 26.23 | -202.34 |
| D_weight_not_aligned_2_2_3 | not_aligned | 1219 | 51.52 | -11078.36 | -31267.14 | -0.35 | 0.955 | -9.09 | -318.78 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 208 | 58.65 | 13574.90 | -4555.38 | 2.98 | 1.349 | 65.26 | -306.49 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 1011 | 50.05 | -24653.26 | -32434.06 | -0.76 | 0.882 | -24.39 | -321.31 |
| E_weight_not_aligned_3_2_3 | aligned | 155 | 58.71 | 4066.16 | -2625.12 | 1.55 | 1.218 | 26.23 | -202.34 |
| E_weight_not_aligned_3_2_3 | not_aligned | 1219 | 51.60 | -12176.72 | -35299.18 | -0.34 | 0.957 | -9.99 | -364.32 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 208 | 58.65 | 15139.30 | -5304.24 | 2.85 | 1.341 | 72.79 | -350.27 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 1011 | 50.15 | -27316.02 | -36378.36 | -0.75 | 0.886 | -27.02 | -367.21 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 155 | 60.65 | 2661.48 | -1554.06 | 1.71 | 1.238 | 17.17 | -121.40 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 1219 | 51.52 | -10065.94 | -26994.23 | -0.37 | 0.953 | -8.26 | -273.24 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 208 | 58.65 | 11404.14 | -4077.47 | 2.80 | 1.342 | 54.83 | -262.70 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 1011 | 50.05 | -21470.08 | -27741.11 | -0.77 | 0.880 | -21.24 | -275.41 |
| G_skip_aligned_not_2_2_3 | not_aligned | 1219 | 51.52 | -11078.36 | -31267.14 | -0.35 | 0.955 | -9.09 | -318.78 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 208 | 58.65 | 13574.90 | -4555.38 | 2.98 | 1.349 | 65.26 | -306.49 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 1011 | 50.05 | -24653.26 | -32434.06 | -0.76 | 0.882 | -24.39 | -321.31 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 582 | 35384.52 | 60.80 |
| A_base_all_1_1_3 | tp2 | 572 | 35067.32 | 61.31 |
| A_base_all_1_1_3 | runner | 1707 | 101155.44 | 59.26 |
| A_base_all_1_1_3 | full_exit | 3960 | -176508.70 | -44.57 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 514 | 31221.10 | 60.74 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 505 | 31307.04 | 61.99 |
| B_hard_filter_not_aligned_1_1_3 | runner | 1506 | 90101.58 | 59.83 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 3525 | -161597.30 | -45.84 |
| C_weight_not_aligned_2_1_3 | tp1 | 1096 | 66605.62 | 60.77 |
| C_weight_not_aligned_2_1_3 | tp2 | 572 | 35067.32 | 61.31 |
| C_weight_not_aligned_2_1_3 | runner | 1707 | 101155.44 | 59.26 |
| C_weight_not_aligned_2_1_3 | full_exit | 4665 | -208828.16 | -44.76 |
| D_weight_not_aligned_2_2_3 | tp1 | 1096 | 66605.62 | 60.77 |
| D_weight_not_aligned_2_2_3 | tp2 | 1077 | 66374.36 | 61.63 |
| D_weight_not_aligned_2_2_3 | runner | 1707 | 101155.44 | 59.26 |
| D_weight_not_aligned_2_2_3 | full_exit | 5370 | -241147.62 | -44.91 |
| E_weight_not_aligned_3_2_3 | tp1 | 1610 | 97826.72 | 60.76 |
| E_weight_not_aligned_3_2_3 | tp2 | 1077 | 66374.36 | 61.63 |
| E_weight_not_aligned_3_2_3 | runner | 1707 | 101155.44 | 59.26 |
| E_weight_not_aligned_3_2_3 | full_exit | 6075 | -273467.08 | -45.02 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 1096 | 66605.62 | 60.77 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 572 | 35067.32 | 61.31 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 1573 | 93786.20 | 59.62 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 4491 | -202863.60 | -45.17 |
| G_skip_aligned_not_2_2_3 | tp1 | 1028 | 62442.20 | 60.74 |
| G_skip_aligned_not_2_2_3 | tp2 | 1010 | 62614.08 | 61.99 |
| G_skip_aligned_not_2_2_3 | runner | 1506 | 90101.58 | 59.83 |
| G_skip_aligned_not_2_2_3 | full_exit | 4935 | -226236.22 | -45.84 |

## Read

- The hard filter is **not** the best allocator answer here: `B_hard_filter_not_aligned_1_1_3` gives up too much net versus the base.
- The cleanest weighted row in this pass is `E_weight_not_aligned_3_2_3`, but it also raises stress and max sizing. It is an allocator optimization candidate, not a first live-test candidate.
- The conservative weighted row `C_weight_not_aligned_2_1_3` improves absolute net while keeping the same aligned participation.
- The prior-opposed subset is the strongest not-aligned branch, matching the timing study's failed-ST/reversal read.

## Files

- `scenario_matrix.csv`
- `regime_decomposition.csv`
- `component_contribution.csv`
- `campaign_regimes.csv`
- `scenario_A_reconstructed_equity.csv`
