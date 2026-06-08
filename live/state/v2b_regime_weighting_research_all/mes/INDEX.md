# MES v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: MES unit trades from `/home/tester/hsm/potions/live/state/v2b_sizing_sweep/states/mes_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session MES hourly ST+PMC `mes_hourly_st_pmc_close_against_entry_next_open`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 661 | 51.89 | -3916.00 | -17843.50 | -0.22 | 0.963 | -5.92 | -248.29 | 6 | 35687.00 | -0.0213 |
| B_hard_filter_not_aligned_1_1_3 | 610 | 50.98 | -2744.50 | -16098.25 | -0.17 | 0.972 | -4.50 | -245.50 | 7 | 40245.62 | -0.0088 |
| C_weight_not_aligned_2_1_3 | 661 | 52.34 | -5467.25 | -21378.25 | -0.26 | 0.957 | -8.27 | -293.60 | 6 | 49169.97 | -0.0166 |
| D_weight_not_aligned_2_2_3 | 661 | 52.50 | -6850.75 | -24671.50 | -0.28 | 0.953 | -10.36 | -338.91 | 6 | 56744.45 | -0.0181 |
| E_weight_not_aligned_3_2_3 | 661 | 52.50 | -8392.00 | -28206.25 | -0.30 | 0.950 | -12.70 | -384.22 | 6 | 64874.37 | -0.0194 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 661 | 52.34 | -4557.25 | -19904.25 | -0.23 | 0.963 | -6.89 | -284.91 | 6 | 45779.77 | -0.0149 |
| G_skip_aligned_not_2_2_3 | 610 | 51.64 | -5679.25 | -23031.50 | -0.25 | 0.959 | -9.31 | -343.70 | 6 | 57578.75 | -0.0128 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 51 | 62.75 | -1171.50 | -3596.50 | -0.33 | 0.852 | -22.97 | -281.62 |
| A_base_all_1_1_3 | not_aligned | 610 | 50.98 | -2744.50 | -16098.25 | -0.17 | 0.972 | -4.50 | -245.50 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 64 | 57.81 | 3395.00 | -4100.00 | 0.83 | 1.317 | 53.05 | -249.32 |
| A_base_all_1_1_3 | not_aligned_no_prior | 546 | 50.18 | -6139.50 | -15222.00 | -0.40 | 0.930 | -11.24 | -245.05 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 610 | 50.98 | -2744.50 | -16098.25 | -0.17 | 0.972 | -4.50 | -245.50 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 64 | 57.81 | 3395.00 | -4100.00 | 0.83 | 1.317 | 53.05 | -249.32 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 546 | 50.18 | -6139.50 | -15222.00 | -0.40 | 0.930 | -11.24 | -245.05 |
| C_weight_not_aligned_2_1_3 | aligned | 51 | 62.75 | -1171.50 | -3596.50 | -0.33 | 0.852 | -22.97 | -281.62 |
| C_weight_not_aligned_2_1_3 | not_aligned | 610 | 51.48 | -4295.75 | -19317.50 | -0.22 | 0.964 | -7.04 | -294.60 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 64 | 57.81 | 3996.50 | -4816.00 | 0.83 | 1.311 | 62.45 | -299.18 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 546 | 50.73 | -8292.25 | -18367.25 | -0.45 | 0.922 | -15.19 | -294.07 |
| D_weight_not_aligned_2_2_3 | aligned | 51 | 62.75 | -1171.50 | -3596.50 | -0.33 | 0.852 | -22.97 | -281.62 |
| D_weight_not_aligned_2_2_3 | not_aligned | 610 | 51.64 | -5679.25 | -23031.50 | -0.25 | 0.959 | -9.31 | -343.70 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 64 | 57.81 | 4573.00 | -5647.00 | 0.81 | 1.305 | 71.45 | -349.04 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 546 | 50.92 | -10252.25 | -21812.25 | -0.47 | 0.917 | -18.78 | -343.08 |
| E_weight_not_aligned_3_2_3 | aligned | 51 | 62.75 | -1171.50 | -3596.50 | -0.33 | 0.852 | -22.97 | -281.62 |
| E_weight_not_aligned_3_2_3 | not_aligned | 610 | 51.64 | -7220.50 | -26250.75 | -0.28 | 0.954 | -11.84 | -392.80 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 64 | 57.81 | 5174.50 | -6393.00 | 0.81 | 1.302 | 80.85 | -398.91 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 546 | 50.92 | -12395.00 | -25081.25 | -0.49 | 0.912 | -22.70 | -392.09 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 51 | 62.75 | -261.50 | -1743.50 | -0.15 | 0.945 | -5.13 | -168.97 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 610 | 51.48 | -4295.75 | -19317.50 | -0.22 | 0.964 | -7.04 | -294.60 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 64 | 57.81 | 3996.50 | -4816.00 | 0.83 | 1.311 | 62.45 | -299.18 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 546 | 50.73 | -8292.25 | -18367.25 | -0.45 | 0.922 | -15.19 | -294.07 |
| G_skip_aligned_not_2_2_3 | not_aligned | 610 | 51.64 | -5679.25 | -23031.50 | -0.25 | 0.959 | -9.31 | -343.70 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 64 | 57.81 | 4573.00 | -5647.00 | 0.81 | 1.305 | 71.45 | -349.04 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 546 | 50.92 | -10252.25 | -21812.25 | -0.47 | 0.917 | -18.78 | -343.08 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 320 | 19147.50 | 59.84 |
| A_base_all_1_1_3 | tp2 | 318 | 18576.75 | 58.42 |
| A_base_all_1_1_3 | runner | 951 | 59488.50 | 62.55 |
| A_base_all_1_1_3 | full_exit | 1705 | -101138.75 | -59.32 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 292 | 17235.75 | 59.03 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 291 | 17393.50 | 59.77 |
| B_hard_filter_not_aligned_1_1_3 | runner | 870 | 56501.25 | 64.94 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 1590 | -93885.00 | -59.05 |
| C_weight_not_aligned_2_1_3 | tp1 | 612 | 36383.25 | 59.45 |
| C_weight_not_aligned_2_1_3 | tp2 | 318 | 18576.75 | 58.42 |
| C_weight_not_aligned_2_1_3 | runner | 951 | 59488.50 | 62.55 |
| C_weight_not_aligned_2_1_3 | full_exit | 2023 | -119915.75 | -59.28 |
| D_weight_not_aligned_2_2_3 | tp1 | 612 | 36383.25 | 59.45 |
| D_weight_not_aligned_2_2_3 | tp2 | 609 | 35970.25 | 59.06 |
| D_weight_not_aligned_2_2_3 | runner | 951 | 59488.50 | 62.55 |
| D_weight_not_aligned_2_2_3 | full_exit | 2341 | -138692.75 | -59.25 |
| E_weight_not_aligned_3_2_3 | tp1 | 904 | 53619.00 | 59.31 |
| E_weight_not_aligned_3_2_3 | tp2 | 609 | 35970.25 | 59.06 |
| E_weight_not_aligned_3_2_3 | runner | 951 | 59488.50 | 62.55 |
| E_weight_not_aligned_3_2_3 | full_exit | 2659 | -157469.75 | -59.22 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 612 | 36383.25 | 59.45 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 318 | 18576.75 | 58.42 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 897 | 57497.00 | 64.10 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 1977 | -117014.25 | -59.19 |
| G_skip_aligned_not_2_2_3 | tp1 | 584 | 34471.50 | 59.03 |
| G_skip_aligned_not_2_2_3 | tp2 | 582 | 34787.00 | 59.77 |
| G_skip_aligned_not_2_2_3 | runner | 870 | 56501.25 | 64.94 |
| G_skip_aligned_not_2_2_3 | full_exit | 2226 | -131439.00 | -59.05 |

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
