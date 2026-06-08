# ES v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: ES unit trades from `/home/tester/hsm/potions/live/state/v2b_sizing_sweep/states/es_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session ES hourly ST+PMC `es_hourly_st_pmc_ma_bull_prior_only`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 1519 | 50.82 | -54265.50 | -269726.50 | -0.20 | 0.978 | -35.72 | -2597.64 | 8 | 539453.00 | -0.0196 |
| B_hard_filter_not_aligned_1_1_3 | 1487 | 50.64 | -58113.00 | -257181.50 | -0.23 | 0.977 | -39.08 | -2600.87 | 7 | 642953.75 | -0.0117 |
| C_weight_not_aligned_2_1_3 | 1519 | 51.48 | -63808.50 | -325462.50 | -0.20 | 0.979 | -42.01 | -3106.85 | 8 | 748563.75 | -0.0128 |
| D_weight_not_aligned_2_2_3 | 1519 | 51.35 | -77820.50 | -374844.00 | -0.21 | 0.978 | -51.23 | -3616.07 | 8 | 862141.20 | -0.0135 |
| E_weight_not_aligned_3_2_3 | 1519 | 51.61 | -87263.50 | -430580.00 | -0.20 | 0.978 | -57.45 | -4125.29 | 8 | 990334.00 | -0.0132 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 1519 | 51.48 | -63537.50 | -317964.50 | -0.20 | 0.979 | -41.83 | -3086.23 | 8 | 731318.35 | -0.0130 |
| G_skip_aligned_not_2_2_3 | 1487 | 51.18 | -81668.00 | -362299.00 | -0.23 | 0.976 | -54.92 | -3641.22 | 7 | 905747.50 | -0.0117 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 32 | 59.38 | 3847.50 | -20145.00 | 0.19 | 1.098 | 120.23 | -2447.27 |
| A_base_all_1_1_3 | not_aligned | 1487 | 50.64 | -58113.00 | -257181.50 | -0.23 | 0.977 | -39.08 | -2600.87 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 35 | 57.14 | 39275.00 | -29062.50 | 1.35 | 1.776 | 1122.14 | -2344.64 |
| A_base_all_1_1_3 | not_aligned_no_prior | 1452 | 50.48 | -97388.00 | -286551.50 | -0.34 | 0.960 | -67.07 | -2607.05 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 1487 | 50.64 | -58113.00 | -257181.50 | -0.23 | 0.977 | -39.08 | -2600.87 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 35 | 57.14 | 39275.00 | -29062.50 | 1.35 | 1.776 | 1122.14 | -2344.64 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 1452 | 50.48 | -97388.00 | -286551.50 | -0.34 | 0.960 | -67.07 | -2607.05 |
| C_weight_not_aligned_2_1_3 | aligned | 32 | 59.38 | 3847.50 | -20145.00 | 0.19 | 1.098 | 120.23 | -2447.27 |
| C_weight_not_aligned_2_1_3 | not_aligned | 1487 | 51.31 | -67656.00 | -312917.50 | -0.22 | 0.977 | -45.50 | -3121.05 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 35 | 57.14 | 44047.50 | -33515.00 | 1.31 | 1.725 | 1258.50 | -2813.57 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 1452 | 51.17 | -111703.50 | -345459.00 | -0.32 | 0.962 | -76.93 | -3128.46 |
| D_weight_not_aligned_2_2_3 | aligned | 32 | 59.38 | 3847.50 | -20145.00 | 0.19 | 1.098 | 120.23 | -2447.27 |
| D_weight_not_aligned_2_2_3 | not_aligned | 1487 | 51.18 | -81668.00 | -362299.00 | -0.23 | 0.976 | -54.92 | -3641.22 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 35 | 57.14 | 50432.50 | -39667.50 | 1.27 | 1.712 | 1440.93 | -3282.50 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 1452 | 51.03 | -132100.50 | -398924.50 | -0.33 | 0.961 | -90.98 | -3649.87 |
| E_weight_not_aligned_3_2_3 | aligned | 32 | 59.38 | 3847.50 | -20145.00 | 0.19 | 1.098 | 120.23 | -2447.27 |
| E_weight_not_aligned_3_2_3 | not_aligned | 1487 | 51.45 | -91111.00 | -418035.00 | -0.22 | 0.977 | -61.27 | -4161.40 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 35 | 57.14 | 55205.00 | -44120.00 | 1.25 | 1.682 | 1577.29 | -3751.43 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 1452 | 51.31 | -146316.00 | -457832.00 | -0.32 | 0.962 | -100.77 | -4171.28 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 32 | 59.38 | 4118.50 | -11587.00 | 0.36 | 1.175 | 128.70 | -1468.36 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 1487 | 51.31 | -67656.00 | -312917.50 | -0.22 | 0.977 | -45.50 | -3121.05 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 35 | 57.14 | 44047.50 | -33515.00 | 1.31 | 1.725 | 1258.50 | -2813.57 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 1452 | 51.17 | -111703.50 | -345459.00 | -0.32 | 0.962 | -76.93 | -3128.46 |
| G_skip_aligned_not_2_2_3 | not_aligned | 1487 | 51.18 | -81668.00 | -362299.00 | -0.23 | 0.976 | -54.92 | -3641.22 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 35 | 57.14 | 50432.50 | -39667.50 | 1.27 | 1.712 | 1440.93 | -3282.50 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 1452 | 51.03 | -132100.50 | -398924.50 | -0.33 | 0.961 | -90.98 | -3649.87 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 726 | 474048.50 | 652.96 |
| A_base_all_1_1_3 | tp2 | 722 | 464779.50 | 643.74 |
| A_base_all_1_1_3 | runner | 2139 | 1401879.00 | 655.39 |
| A_base_all_1_1_3 | full_exit | 3965 | -2395072.50 | -604.05 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 709 | 462399.00 | 652.18 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 705 | 457830.00 | 649.40 |
| B_hard_filter_not_aligned_1_1_3 | runner | 2088 | 1380768.00 | 661.29 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 3890 | -2359210.00 | -606.48 |
| C_weight_not_aligned_2_1_3 | tp1 | 1435 | 936447.50 | 652.58 |
| C_weight_not_aligned_2_1_3 | tp2 | 722 | 464779.50 | 643.74 |
| C_weight_not_aligned_2_1_3 | runner | 2139 | 1401879.00 | 655.39 |
| C_weight_not_aligned_2_1_3 | full_exit | 4743 | -2866914.50 | -604.45 |
| D_weight_not_aligned_2_2_3 | tp1 | 1435 | 936447.50 | 652.58 |
| D_weight_not_aligned_2_2_3 | tp2 | 1427 | 922609.50 | 646.54 |
| D_weight_not_aligned_2_2_3 | runner | 2139 | 1401879.00 | 655.39 |
| D_weight_not_aligned_2_2_3 | full_exit | 5521 | -3338756.50 | -604.74 |
| E_weight_not_aligned_3_2_3 | tp1 | 2144 | 1398846.50 | 652.45 |
| E_weight_not_aligned_3_2_3 | tp2 | 1427 | 922609.50 | 646.54 |
| E_weight_not_aligned_3_2_3 | runner | 2139 | 1401879.00 | 655.39 |
| E_weight_not_aligned_3_2_3 | full_exit | 6299 | -3810598.50 | -604.95 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 1435 | 936447.50 | 652.58 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 722 | 464779.50 | 643.74 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 2105 | 1387805.00 | 659.29 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 4713 | -2852569.50 | -605.26 |
| G_skip_aligned_not_2_2_3 | tp1 | 1418 | 924798.00 | 652.18 |
| G_skip_aligned_not_2_2_3 | tp2 | 1410 | 915660.00 | 649.40 |
| G_skip_aligned_not_2_2_3 | runner | 2088 | 1380768.00 | 661.29 |
| G_skip_aligned_not_2_2_3 | full_exit | 5446 | -3302894.00 | -606.48 |

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
