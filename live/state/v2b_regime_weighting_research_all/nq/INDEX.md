# NQ v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: NQ unit trades from `/home/tester/hsm/potions/live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/unit_trades.csv`.
- Regime signal: prior same-session NQ hourly ST+PMC `nq_hourly_st_pmc_sl25_tp75_3r`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

| row | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae | max_losing_streak | stress_capital | dce |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | 1386 | 53.82 | 867355.00 | -100085.00 | 8.67 | 1.189 | 625.80 | -5625.92 | 6 | 200170.00 | 0.8430 |
| B_hard_filter_not_aligned_1_1_3 | 1256 | 53.98 | 823410.00 | -111201.50 | 7.40 | 1.200 | 655.58 | -5610.99 | 8 | 278003.75 | 0.3842 |
| C_weight_not_aligned_2_1_3 | 1386 | 54.40 | 1011896.00 | -118356.50 | 8.55 | 1.187 | 730.08 | -6642.86 | 6 | 272219.95 | 0.5563 |
| D_weight_not_aligned_2_2_3 | 1386 | 54.18 | 1169171.50 | -145372.50 | 8.04 | 1.188 | 843.56 | -7659.80 | 6 | 334356.75 | 0.5233 |
| E_weight_not_aligned_3_2_3 | 1386 | 54.55 | 1313712.50 | -171860.00 | 7.64 | 1.186 | 947.84 | -8676.74 | 6 | 395278.00 | 0.4974 |
| F_derisk_aligned_1_1_1_not_2_1_3 | 1386 | 54.47 | 984186.00 | -117724.00 | 8.36 | 1.189 | 710.09 | -6426.37 | 6 | 270765.20 | 0.5440 |
| G_skip_aligned_not_2_2_3 | 1256 | 54.38 | 1125226.50 | -146059.00 | 7.70 | 1.196 | 895.88 | -7855.38 | 8 | 365147.50 | 0.3997 |

## Regime Decomposition

| scenario | regime | trades | win_rate_pct | net_usd | stress_dd_usd | net_stress | profit_factor | avg_trade | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | aligned | 130 | 52.31 | 43945.00 | -83270.00 | 0.53 | 1.091 | 338.04 | -5770.19 |
| A_base_all_1_1_3 | not_aligned | 1256 | 53.98 | 823410.00 | -111201.50 | 7.40 | 1.200 | 655.58 | -5610.99 |
| A_base_all_1_1_3 | not_aligned_prior_opposed | 184 | 66.30 | 616085.00 | -54742.50 | 11.25 | 2.354 | 3348.29 | -5102.04 |
| A_base_all_1_1_3 | not_aligned_no_prior | 1072 | 51.87 | 207325.00 | -189794.50 | 1.09 | 1.057 | 193.40 | -5698.34 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned | 1256 | 53.98 | 823410.00 | -111201.50 | 7.40 | 1.200 | 655.58 | -5610.99 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_prior_opposed | 184 | 66.30 | 616085.00 | -54742.50 | 11.25 | 2.354 | 3348.29 | -5102.04 |
| B_hard_filter_not_aligned_1_1_3 | not_aligned_no_prior | 1072 | 51.87 | 207325.00 | -189794.50 | 1.09 | 1.057 | 193.40 | -5698.34 |
| C_weight_not_aligned_2_1_3 | aligned | 130 | 52.31 | 43945.00 | -83270.00 | 0.53 | 1.091 | 338.04 | -5770.19 |
| C_weight_not_aligned_2_1_3 | not_aligned | 1256 | 54.62 | 967951.00 | -128266.00 | 7.55 | 1.197 | 770.66 | -6733.18 |
| C_weight_not_aligned_2_1_3 | not_aligned_prior_opposed | 184 | 67.93 | 705089.00 | -62811.00 | 11.23 | 2.301 | 3832.01 | -6122.45 |
| C_weight_not_aligned_2_1_3 | not_aligned_no_prior | 1072 | 52.33 | 262862.00 | -212575.50 | 1.24 | 1.060 | 245.21 | -6838.01 |
| D_weight_not_aligned_2_2_3 | aligned | 130 | 52.31 | 43945.00 | -83270.00 | 0.53 | 1.091 | 338.04 | -5770.19 |
| D_weight_not_aligned_2_2_3 | not_aligned | 1256 | 54.38 | 1125226.50 | -146059.00 | 7.70 | 1.196 | 895.88 | -7855.38 |
| D_weight_not_aligned_2_2_3 | not_aligned_prior_opposed | 184 | 66.85 | 809713.00 | -72604.50 | 11.15 | 2.279 | 4400.61 | -7142.85 |
| D_weight_not_aligned_2_2_3 | not_aligned_no_prior | 1072 | 52.24 | 315513.50 | -241940.00 | 1.30 | 1.062 | 294.32 | -7977.68 |
| E_weight_not_aligned_3_2_3 | aligned | 130 | 52.31 | 43945.00 | -83270.00 | 0.53 | 1.091 | 338.04 | -5770.19 |
| E_weight_not_aligned_3_2_3 | not_aligned | 1256 | 54.78 | 1269767.50 | -163123.50 | 7.78 | 1.194 | 1010.96 | -8977.58 |
| E_weight_not_aligned_3_2_3 | not_aligned_prior_opposed | 184 | 67.93 | 898717.00 | -80673.00 | 11.14 | 2.244 | 4884.33 | -8163.26 |
| E_weight_not_aligned_3_2_3 | not_aligned_no_prior | 1072 | 52.52 | 371050.50 | -264721.00 | 1.40 | 1.064 | 346.13 | -9117.35 |
| F_derisk_aligned_1_1_1_not_2_1_3 | aligned | 130 | 53.08 | 16235.00 | -51776.50 | 0.31 | 1.056 | 124.88 | -3462.12 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned | 1256 | 54.62 | 967951.00 | -128266.00 | 7.55 | 1.197 | 770.66 | -6733.18 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_prior_opposed | 184 | 67.93 | 705089.00 | -62811.00 | 11.23 | 2.301 | 3832.01 | -6122.45 |
| F_derisk_aligned_1_1_1_not_2_1_3 | not_aligned_no_prior | 1072 | 52.33 | 262862.00 | -212575.50 | 1.24 | 1.060 | 245.21 | -6838.01 |
| G_skip_aligned_not_2_2_3 | not_aligned | 1256 | 54.38 | 1125226.50 | -146059.00 | 7.70 | 1.196 | 895.88 | -7855.38 |
| G_skip_aligned_not_2_2_3 | not_aligned_prior_opposed | 184 | 66.85 | 809713.00 | -72604.50 | 11.15 | 2.279 | 4400.61 | -7142.85 |
| G_skip_aligned_not_2_2_3 | not_aligned_no_prior | 1072 | 52.24 | 315513.50 | -241940.00 | 1.30 | 1.062 | 294.32 | -7977.68 |

## Component Contribution

| scenario | bucket | units | net_usd | avg_unit |
| --- | --- | --- | --- | --- |
| A_base_all_1_1_3 | tp1 | 656 | 984526.00 | 1500.80 |
| A_base_all_1_1_3 | tp2 | 653 | 1005420.50 | 1539.69 |
| A_base_all_1_1_3 | runner | 1941 | 3088273.50 | 1591.07 |
| A_base_all_1_1_3 | full_exit | 3650 | -4212425.00 | -1154.09 |
| B_hard_filter_not_aligned_1_1_3 | tp1 | 591 | 892333.50 | 1509.87 |
| B_hard_filter_not_aligned_1_1_3 | tp2 | 588 | 905068.00 | 1539.23 |
| B_hard_filter_not_aligned_1_1_3 | runner | 1746 | 2764971.00 | 1583.60 |
| B_hard_filter_not_aligned_1_1_3 | full_exit | 3325 | -3738962.50 | -1124.50 |
| C_weight_not_aligned_2_1_3 | tp1 | 1247 | 1876859.50 | 1505.10 |
| C_weight_not_aligned_2_1_3 | tp2 | 653 | 1005420.50 | 1539.69 |
| C_weight_not_aligned_2_1_3 | runner | 1941 | 3088273.50 | 1591.07 |
| C_weight_not_aligned_2_1_3 | full_exit | 4315 | -4960217.50 | -1149.53 |
| D_weight_not_aligned_2_2_3 | tp1 | 1247 | 1876859.50 | 1505.10 |
| D_weight_not_aligned_2_2_3 | tp2 | 1241 | 1910488.50 | 1539.48 |
| D_weight_not_aligned_2_2_3 | runner | 1941 | 3088273.50 | 1591.07 |
| D_weight_not_aligned_2_2_3 | full_exit | 4980 | -5708010.00 | -1146.19 |
| E_weight_not_aligned_3_2_3 | tp1 | 1838 | 2769193.00 | 1506.63 |
| E_weight_not_aligned_3_2_3 | tp2 | 1241 | 1910488.50 | 1539.48 |
| E_weight_not_aligned_3_2_3 | runner | 1941 | 3088273.50 | 1591.07 |
| E_weight_not_aligned_3_2_3 | full_exit | 5645 | -6455802.50 | -1143.63 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp1 | 1247 | 1876859.50 | 1505.10 |
| F_derisk_aligned_1_1_1_not_2_1_3 | tp2 | 653 | 1005420.50 | 1539.69 |
| F_derisk_aligned_1_1_1_not_2_1_3 | runner | 1811 | 2872738.50 | 1586.27 |
| F_derisk_aligned_1_1_1_not_2_1_3 | full_exit | 4185 | -4770832.50 | -1139.98 |
| G_skip_aligned_not_2_2_3 | tp1 | 1182 | 1784667.00 | 1509.87 |
| G_skip_aligned_not_2_2_3 | tp2 | 1176 | 1810136.00 | 1539.23 |
| G_skip_aligned_not_2_2_3 | runner | 1746 | 2764971.00 | 1583.60 |
| G_skip_aligned_not_2_2_3 | full_exit | 4655 | -5234547.50 | -1124.50 |

## Read

- The hard filter is **not** the best allocator answer here: `B_hard_filter_not_aligned_1_1_3` gives up too much net versus the base.
- The cleanest weighted row in this pass is `E_weight_not_aligned_3_2_3`, but it also raises stress and max sizing. It is an allocator optimization candidate, not a first live-test candidate.
- The conservative weighted row `C_weight_not_aligned_2_1_3` improves absolute net while keeping the same aligned participation.
- The prior-opposed subset is the strongest not-aligned branch, matching the timing study's failed-ST/reversal read.
- Full broker-like confirmation exists for the prior-opposed branch as a true delayed-arming `StrategyPlugin` gate: [`../../nq_v2b_prior_opposed_stpmc_broker_like/INDEX.md`](../../nq_v2b_prior_opposed_stpmc_broker_like/INDEX.md). That replay produced **$1,184,585 / -$53,847 stress / 22.00 Net-Stress** and has a complete 15m chart pack at [`../../nq_v2b_prior_opposed_stpmc_broker_like/charts/prior_opposed_15m/INDEX.md`](../../nq_v2b_prior_opposed_stpmc_broker_like/charts/prior_opposed_15m/INDEX.md). Robustness audit is here: [`../../nq_v2b_prior_opposed_stpmc_broker_like/robustness_audit/ROBUSTNESS_AUDIT.md`](../../nq_v2b_prior_opposed_stpmc_broker_like/robustness_audit/ROBUSTNESS_AUDIT.md).

## Files

- `scenario_matrix.csv`
- `regime_decomposition.csv`
- `component_contribution.csv`
- `campaign_regimes.csv`
- `scenario_A_reconstructed_equity.csv`
