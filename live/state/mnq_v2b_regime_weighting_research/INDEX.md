# MNQ v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

> **2026-06-06 strict replay supersession.** This page is an after-the-fact
> unit-tape regime-weighting study. The MNQ prior-opposed branch has now been
> rebuilt as a true delayed-arming `StrategyPlugin` replay: **353 campaigns /
> $113,547.50 net / -$5,418 intrabar stress / 20.96 Net/Stress / 0 causal
> violations**. Use
> [`../mnq_v2b_prior_opposed_stpmc_broker_like/INDEX.md`](../mnq_v2b_prior_opposed_stpmc_broker_like/INDEX.md)
> for promotion decisions; keep this page for allocator context and historical
> research lineage.

Model:

- Base v2b tape: MNQ `S_1_1_3` unit trades from `live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session MNQ hourly ST+PMC `mnq_hourly_st_pmc_sl25_tp75_3r`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 1384 | 53.61 | 74441.50 | -10245.50 | 7.27 | 1.160 | 53.79 | -566.05 | 6 | 20491.00 | 0.7068 |
| B_hard_filter_not_aligned_1_1_3 | 1252 | 53.67 | 70667.00 | -11906.50 | 5.94 | 1.170 | 56.44 | -564.89 | 8 | 29766.25 | 0.3079 |
| C_weight_not_aligned_2_1_3 | 1384 | 54.19 | 86673.50 | -12399.00 | 6.99 | 1.159 | 62.63 | -668.26 | 6 | 28517.70 | 0.4548 |
| D_weight_not_aligned_2_2_3 | 1384 | 54.05 | 99991.50 | -14398.00 | 6.94 | 1.159 | 72.25 | -770.46 | 6 | 33115.40 | 0.4519 |
| E_weight_not_aligned_3_2_3 | 1384 | 54.41 | 112223.50 | -16903.50 | 6.64 | 1.158 | 81.09 | -872.66 | 6 | 38878.05 | 0.4320 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 1384 | 54.26 | 84155.50 | -12367.00 | 6.80 | 1.160 | 60.81 | -646.24 | 6 | 28444.10 | 0.4428 |
| G_skip_aligned_not_2_2_3 | 1252 | 54.15 | 96217.00 | -16043.00 | 6.00 | 1.166 | 76.85 | -790.84 | 8 | 40107.50 | 0.3112 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 132 | 53.03 | 3774.50 | -7535.00 | 0.50 | 1.077 | 28.59 | -577.14 |
| A_base_all_1_1_3 | not_aligned | 1252 | 53.67 | 70667.00 | -11906.50 | 5.94 | 1.170 | 56.44 | -564.89 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 183 | 66.12 | 57668.50 | -5606.50 | 10.29 | 2.237 | 315.13 | -519.03 |
| A_base_all_1_1_3 | not_aligned_no_prior | 1069 | 51.54 | 12998.50 | -19628.50 | 0.66 | 1.035 | 12.16 | -572.74 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 1252 | 53.67 | 70667.00 | -11906.50 | 5.94 | 1.170 | 56.44 | -564.89 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 183 | 66.12 | 57668.50 | -5606.50 | 10.29 | 2.237 | 315.13 | -519.03 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 1069 | 51.54 | 12998.50 | -19628.50 | 0.66 | 1.035 | 12.16 | -572.74 |
| C_weight_not_aligned_2_1_3 | aligned | 132 | 53.03 | 3774.50 | -7535.00 | 0.50 | 1.077 | 28.59 | -577.14 |
| C_weight_not_aligned_2_1_3 | not_aligned | 1252 | 54.31 | 82899.00 | -14092.00 | 5.88 | 1.167 | 66.21 | -677.86 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 183 | 67.76 | 66020.50 | -6439.00 | 10.25 | 2.189 | 360.77 | -622.84 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 1069 | 52.01 | 16878.50 | -22059.50 | 0.77 | 1.038 | 15.79 | -687.28 |
| D_weight_not_aligned_2_2_3 | aligned | 132 | 53.03 | 3774.50 | -7535.00 | 0.50 | 1.077 | 28.59 | -577.14 |
| D_weight_not_aligned_2_2_3 | not_aligned | 1252 | 54.15 | 96217.00 | -16043.00 | 6.00 | 1.166 | 76.85 | -790.84 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 183 | 66.67 | 75621.50 | -7443.50 | 10.16 | 2.165 | 413.23 | -726.64 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 1069 | 52.01 | 20595.50 | -25098.50 | 0.82 | 1.040 | 19.27 | -801.83 |
| E_weight_not_aligned_3_2_3 | aligned | 132 | 53.03 | 3774.50 | -7535.00 | 0.50 | 1.077 | 28.59 | -577.14 |
| E_weight_not_aligned_3_2_3 | not_aligned | 1252 | 54.55 | 108449.00 | -18539.00 | 5.85 | 1.164 | 86.62 | -903.82 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 183 | 67.76 | 83973.50 | -8276.00 | 10.15 | 2.135 | 458.87 | -830.45 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 1069 | 52.29 | 24475.50 | -27529.50 | 0.89 | 1.042 | 22.90 | -916.38 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 132 | 53.79 | 1256.50 | -4586.50 | 0.27 | 1.043 | 9.52 | -346.28 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 1252 | 54.31 | 82899.00 | -14092.00 | 5.88 | 1.167 | 66.21 | -677.86 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 183 | 67.76 | 66020.50 | -6439.00 | 10.25 | 2.189 | 360.77 | -622.84 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 1069 | 52.01 | 16878.50 | -22059.50 | 0.77 | 1.038 | 15.79 | -687.28 |
| G_skip_aligned_not_2_2_3 | not_aligned | 1252 | 54.15 | 96217.00 | -16043.00 | 6.00 | 1.166 | 76.85 | -790.84 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 183 | 66.67 | 75621.50 | -7443.50 | 10.16 | 2.165 | 413.23 | -726.64 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 1069 | 52.01 | 20595.50 | -25098.50 | 0.82 | 1.040 | 19.27 | -801.83 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 651 | 97076.00 | 149.12 |
| A_base_all_1_1_3 | tp2 | 647 | 98854.00 | 152.79 |
| A_base_all_1_1_3 | runner | 1923 | 304119.00 | 158.15 |
| A_base_all_1_1_3 | full_exit | 3665 | -425762.50 | -116.17 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 585 | 87732.00 | 149.97 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 581 | 88818.00 | 152.87 |
| B_hard_filter_not_aligned_1_1_3 | runner | 1725 | 271617.00 | 157.46 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 3335 | -377500.00 | -113.19 |
| C_weight_not_aligned_2_1_3 | tp1 | 1236 | 184808.00 | 149.52 |
| C_weight_not_aligned_2_1_3 | tp2 | 647 | 98854.00 | 152.79 |
| C_weight_not_aligned_2_1_3 | runner | 1923 | 304119.00 | 158.15 |
| C_weight_not_aligned_2_1_3 | full_exit | 4332 | -501262.50 | -115.71 |
| D_weight_not_aligned_2_2_3 | tp1 | 1236 | 184808.00 | 149.52 |
| D_weight_not_aligned_2_2_3 | tp2 | 1228 | 187672.00 | 152.83 |
| D_weight_not_aligned_2_2_3 | runner | 1923 | 304119.00 | 158.15 |
| D_weight_not_aligned_2_2_3 | full_exit | 4999 | -576762.50 | -115.38 |
| E_weight_not_aligned_3_2_3 | tp1 | 1821 | 272540.00 | 149.67 |
| E_weight_not_aligned_3_2_3 | tp2 | 1228 | 187672.00 | 152.83 |
| E_weight_not_aligned_3_2_3 | runner | 1923 | 304119.00 | 158.15 |
| E_weight_not_aligned_3_2_3 | full_exit | 5666 | -652262.50 | -115.12 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 1236 | 184808.00 | 149.52 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 647 | 98854.00 | 152.79 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 1791 | 282451.00 | 157.71 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 4200 | -481957.50 | -114.75 |
| G_skip_aligned_not_2_2_3 | tp1 | 1170 | 175464.00 | 149.97 |
| G_skip_aligned_not_2_2_3 | tp2 | 1162 | 177636.00 | 152.87 |
| G_skip_aligned_not_2_2_3 | runner | 1725 | 271617.00 | 157.46 |
| G_skip_aligned_not_2_2_3 | full_exit | 4669 | -528500.00 | -113.19 |

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
