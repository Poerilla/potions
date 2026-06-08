# YM Hourly ST + PMC Loss Research

This batch profiles the existing broker-like loss tape and runs fast broker-like variants.

Simulation assumptions:
- Resting entry limits fill before the current bar's strategy refresh/cancel, matching the Engine/PaperBroker ordering.
- Fresh or modified entry limits become live only after the confirming hourly bar.
- Protective stops fill before targets in same-bar ambiguity.
- Stops and market exits carry 1 tick adverse slippage; unit exits include a $1.50 fee.
- Scaleout runner stop moves to entry after TP1, effective from the next bar because the sequence inside that TP1 bar is unknowable.

## Variant Sweep

| Rank | Variant | Units | Trades | Net | Stress DD | Net/Stress | PF | Win Rate | Max Open | Notes |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `sl35_tp105_3r` | 2,104 | 2,104 | $64,053.98 | $-7,482.07 | 8.56 | 1.24 | 30.5% | 1 | Tighter 35 point stop, 3R target. |
| 2 | `sl40_tp120_3r` | 2,017 | 2,017 | $71,989.69 | $-10,558.07 | 6.82 | 1.24 | 30.4% | 1 | Tighter 40 point stop, 3R target. |
| 3 | `sl25_tp75_3r` | 2,333 | 2,333 | $33,428.80 | $-5,702.81 | 5.86 | 1.15 | 29.3% | 1 | Very tight 25 point stop, 3R target. |
| 4 | `ma_bull_prior_only` | 976 | 976 | $38,828.17 | $-6,862.40 | 5.66 | 1.22 | 29.6% | 1 | V2B-style prior MA50>MA150 on/off gate; keeps both ST/PMC long and short signals. |
| 5 | `ma_directional_prior` | 1,416 | 1,416 | $53,545.07 | $-10,405.19 | 5.15 | 1.21 | 29.5% | 1 | Long only when prior completed hourly MA50>MA150; short only when prior MA50<MA150. |
| 6 | `close_against_entry_next_open` | 1,936 | 1,936 | $62,209.07 | $-12,101.30 | 5.14 | 1.26 | 21.4% | 1 | If an hourly close is adverse to entry, flatten next bar open with market slippage. |
| 7 | `ma_directional_current` | 1,422 | 1,422 | $51,001.07 | $-11,297.30 | 4.51 | 1.20 | 29.3% | 1 | Long only when current hourly MA50>MA150; short only when MA50<MA150. |
| 8 | `st_flip_exit_next_open` | 1,939 | 1,939 | $60,898.59 | $-13,730.66 | 4.44 | 1.25 | 22.2% | 1 | If hourly Supertrend flips against the position, flatten next bar open. |
| 9 | `ma_directional_prior_close_against` | 1,488 | 1,488 | $49,002.53 | $-11,498.40 | 4.26 | 1.26 | 21.4% | 1 | Directional prior MA filter plus adverse-close flatten. |
| 10 | `sl35_tp150_fixed` | 1,937 | 1,937 | $49,836.07 | $-11,732.47 | 4.25 | 1.18 | 22.6% | 1 | Tighter 35 point stop, original 150 target. |
| 11 | `sl40_tp150_fixed` | 1,903 | 1,903 | $57,762.29 | $-14,636.49 | 3.95 | 1.19 | 25.1% | 1 | Tighter 40 point stop, original 150 target. |
| 12 | `base_1x_50sl_150tp` | 1,841 | 1,841 | $62,237.29 | $-16,231.78 | 3.83 | 1.18 | 29.2% | 1 | Current one-unit 50/150 replay rule in fast broker-like simulator. |
| 13 | `pmc_cross_exit_next_open` | 1,874 | 1,874 | $56,632.27 | $-17,024.41 | 3.33 | 1.18 | 30.0% | 1 | If close crosses back through prior month close against the position, flatten next bar open. |
| 14 | `scaleout2_tp3r_runner6r_ma_directional_prior` | 2,470 | 1,235 | $91,693.18 | $-29,566.07 | 3.10 | 1.20 | 22.2% | 2 | Scaleout 2 with prior completed hourly MA direction filter. |
| 15 | `scaleout2_tp3r_runner6r_close_against` | 3,536 | 1,768 | $94,404.92 | $-32,397.87 | 2.91 | 1.21 | 15.9% | 2 | Scaleout 2 with adverse-close flatten. |
| 16 | `scaleout2_tp3r_runner6r` | 3,206 | 1,603 | $100,510.26 | $-39,996.50 | 2.51 | 1.17 | 21.9% | 2 | Enter 2: one off at 3R, runner target 6R, runner stop moves to entry after TP1. |
| 17 | `sl25_tp150_fixed` | 2,038 | 2,038 | $24,805.31 | $-14,273.42 | 1.74 | 1.11 | 16.6% | 1 | Very tight 25 point stop, original 150 target. |
| 18 | `ma_bear_prior_only` | 891 | 891 | $23,775.12 | $-18,538.93 | 1.28 | 1.14 | 28.6% | 1 | Inverse prior MA50<MA150 gate; useful to see whether losses cluster in bearish regimes. |

## Loss Profile Source

Loss profiling tables use `actual_engine_base`.

## Key Profile Tables

- `loss_profile_by_side_ma_prior.csv` (4 rows)
- `loss_profile_by_side_ma_current.csv` (4 rows)
- `loss_profile_by_ma_prior_alignment.csv` (2 rows)
- `loss_profile_by_hour.csv` (24 rows)
- `loss_profile_by_rth.csv` (2 rows)
- `loss_profile_by_month.csv` (12 rows)
- `loss_profile_by_year.csv` (17 rows)
- `loss_profile_by_exit_reason.csv` (2 rows)
- `loss_streaks.csv` (16 rows)

## Quick Reads To Check First

- `loss_profile_by_side_ma_prior.csv`: whether shorts lose inside bullish hourly MA regimes, or longs lose inside bearish regimes.
- `loss_profile_by_hour.csv`: whether losses cluster around specific sessions.
- `loss_profile_by_exit_reason.csv`: whether proposed clip rules reduce loss dollars or mostly cut winners.
- `variant_summary.csv`: the horse race between MA filters, tighter stops, adverse-close exits, and the 2-lot 3R/6R scaleout.

## Charts

- `charts/variant_net_vs_stress.png`
- `charts/profile_side_ma_prior_net.png`
- `charts/profile_hour_net.png`
