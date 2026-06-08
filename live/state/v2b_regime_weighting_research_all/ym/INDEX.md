# YM v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: YM unit trades from `/home/tester/hsm/potions/live/state/v2b_sizing_sweep/states/ym_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session YM hourly ST+PMC `ym_hourly_st_pmc_ma_bull_prior_only`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 1403 | 52.67 | 37689.75 | -204425.25 | 0.18 | 1.019 | 26.86 | -2298.53 | 10 | 408850.50 | 0.0179 |
| B_hard_filter_not_aligned_1_1_3 | 1319 | 52.08 | 28673.50 | -207594.00 | 0.14 | 1.015 | 21.74 | -2321.06 | 12 | 518985.00 | 0.0072 |
| C_weight_not_aligned_2_1_3 | 1403 | 52.82 | 48776.25 | -238822.25 | 0.20 | 1.020 | 34.77 | -2734.95 | 10 | 549291.17 | 0.0133 |
| D_weight_not_aligned_2_2_3 | 1403 | 52.82 | 56925.25 | -277595.75 | 0.21 | 1.020 | 40.57 | -3171.37 | 10 | 638470.22 | 0.0133 |
| E_weight_not_aligned_3_2_3 | 1403 | 52.89 | 66605.50 | -314142.75 | 0.21 | 1.021 | 47.47 | -3607.79 | 10 | 722528.32 | 0.0138 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 1403 | 52.82 | 49758.25 | -237531.75 | 0.21 | 1.021 | 35.47 | -2688.38 | 10 | 546323.02 | 0.0136 |
| G_skip_aligned_not_2_2_3 | 1319 | 52.24 | 47909.00 | -280764.50 | 0.17 | 1.018 | 36.32 | -3249.49 | 12 | 701911.25 | 0.0089 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 84 | 61.90 | 9016.25 | -34381.25 | 0.26 | 1.099 | 107.34 | -1944.72 |
| A_base_all_1_1_3 | not_aligned | 1319 | 52.08 | 28673.50 | -207594.00 | 0.14 | 1.015 | 21.74 | -2321.06 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 120 | 55.83 | 36893.75 | -39501.25 | 0.93 | 1.242 | 307.45 | -2121.35 |
| A_base_all_1_1_3 | not_aligned_no_prior | 1199 | 51.71 | -8220.25 | -218747.75 | -0.04 | 0.995 | -6.86 | -2341.05 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 1319 | 52.08 | 28673.50 | -207594.00 | 0.14 | 1.015 | 21.74 | -2321.06 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 120 | 55.83 | 36893.75 | -39501.25 | 0.93 | 1.242 | 307.45 | -2121.35 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 1199 | 51.71 | -8220.25 | -218747.75 | -0.04 | 0.995 | -6.86 | -2341.05 |
| C_weight_not_aligned_2_1_3 | aligned | 84 | 61.90 | 9016.25 | -34381.25 | 0.26 | 1.099 | 107.34 | -1944.72 |
| C_weight_not_aligned_2_1_3 | not_aligned | 1319 | 52.24 | 39760.00 | -241991.00 | 0.16 | 1.017 | 30.14 | -2785.27 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 120 | 55.83 | 44211.25 | -46511.25 | 0.95 | 1.242 | 368.43 | -2545.62 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 1199 | 51.88 | -4451.25 | -253926.75 | -0.02 | 0.998 | -3.71 | -2809.26 |
| D_weight_not_aligned_2_2_3 | aligned | 84 | 61.90 | 9016.25 | -34381.25 | 0.26 | 1.099 | 107.34 | -1944.72 |
| D_weight_not_aligned_2_2_3 | not_aligned | 1319 | 52.24 | 47909.00 | -280764.50 | 0.17 | 1.018 | 36.32 | -3249.49 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 120 | 55.83 | 51360.00 | -53948.75 | 0.95 | 1.241 | 428.00 | -2969.90 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 1199 | 51.88 | -3451.00 | -296076.25 | -0.01 | 0.999 | -2.88 | -3277.47 |
| E_weight_not_aligned_3_2_3 | aligned | 84 | 61.90 | 9016.25 | -34381.25 | 0.26 | 1.099 | 107.34 | -1944.72 |
| E_weight_not_aligned_3_2_3 | not_aligned | 1319 | 52.31 | 57589.25 | -317311.50 | 0.18 | 1.019 | 43.66 | -3713.70 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 120 | 55.83 | 56582.50 | -61067.75 | 0.93 | 1.232 | 471.52 | -3394.17 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 1199 | 51.96 | 1006.75 | -332452.25 | 0.00 | 1.000 | 0.84 | -3745.68 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 84 | 61.90 | 9998.25 | -19302.25 | 0.52 | 1.184 | 119.03 | -1166.83 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 1319 | 52.24 | 39760.00 | -241991.00 | 0.16 | 1.017 | 30.14 | -2785.27 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 120 | 55.83 | 44211.25 | -46511.25 | 0.95 | 1.242 | 368.43 | -2545.62 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 1199 | 51.88 | -4451.25 | -253926.75 | -0.02 | 0.998 | -3.71 | -2809.26 |
| G_skip_aligned_not_2_2_3 | not_aligned | 1319 | 52.24 | 47909.00 | -280764.50 | 0.17 | 1.018 | 36.32 | -3249.49 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 120 | 55.83 | 51360.00 | -53948.75 | 0.95 | 1.241 | 428.00 | -2969.90 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 1199 | 51.88 | -3451.00 | -296076.25 | -0.01 | 0.999 | -2.88 | -3277.47 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 600 | 375811.25 | 626.35 |
| A_base_all_1_1_3 | tp2 | 590 | 374153.75 | 634.16 |
| A_base_all_1_1_3 | runner | 1761 | 1093247.25 | 620.81 |
| A_base_all_1_1_3 | full_exit | 4015 | -1804116.25 | -449.34 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 566 | 356297.25 | 629.50 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 556 | 354766.00 | 638.07 |
| B_hard_filter_not_aligned_1_1_3 | runner | 1659 | 1052101.50 | 634.18 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 3765 | -1733085.00 | -460.31 |
| C_weight_not_aligned_2_1_3 | tp1 | 1166 | 732108.50 | 627.88 |
| C_weight_not_aligned_2_1_3 | tp2 | 590 | 374153.75 | 634.16 |
| C_weight_not_aligned_2_1_3 | runner | 1761 | 1093247.25 | 620.81 |
| C_weight_not_aligned_2_1_3 | full_exit | 4768 | -2150733.25 | -451.08 |
| D_weight_not_aligned_2_2_3 | tp1 | 1166 | 732108.50 | 627.88 |
| D_weight_not_aligned_2_2_3 | tp2 | 1146 | 728919.75 | 636.06 |
| D_weight_not_aligned_2_2_3 | runner | 1761 | 1093247.25 | 620.81 |
| D_weight_not_aligned_2_2_3 | full_exit | 5521 | -2497350.25 | -452.34 |
| E_weight_not_aligned_3_2_3 | tp1 | 1732 | 1088405.75 | 628.41 |
| E_weight_not_aligned_3_2_3 | tp2 | 1146 | 728919.75 | 636.06 |
| E_weight_not_aligned_3_2_3 | runner | 1761 | 1093247.25 | 620.81 |
| E_weight_not_aligned_3_2_3 | full_exit | 6274 | -2843967.25 | -453.29 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 1166 | 732108.50 | 627.88 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 590 | 374153.75 | 634.16 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 1693 | 1065816.75 | 629.54 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 4668 | -2122320.75 | -454.65 |
| G_skip_aligned_not_2_2_3 | tp1 | 1132 | 712594.50 | 629.50 |
| G_skip_aligned_not_2_2_3 | tp2 | 1112 | 709532.00 | 638.07 |
| G_skip_aligned_not_2_2_3 | runner | 1659 | 1052101.50 | 634.18 |
| G_skip_aligned_not_2_2_3 | full_exit | 5271 | -2426319.00 | -460.31 |

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
