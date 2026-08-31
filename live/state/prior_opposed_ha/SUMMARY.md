# Prior-opposed Heikin Ashi overlay

Diagnostic. Causal 5m HA (bar must complete before entry). Prior-opposed trades are **counter-trend vs implied ST** by construction (implied ST = opposite of the PO side).

- **ha_with_fade** — HA color agrees with the prior-opposed trade (HA also fading ST).
- **ha_with_prior_trend** — HA still points with implied ST (trend-continuation pressure vs the fade).

Current-condition columns are the existing futures HP profile (OR-norm, ST-age, RSI, 5m MA).

## nq_prior_opposed_rl

Baseline n=432 WR=66.0% net=$1330920 N/S=24.06

### HA vs PO / ST

| condition | bucket | n | wr | avg_net | net | ns | wr_lift_pp | z_wr |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| HA vs prior-opposed | ha_with_prior_trend | 105 | 71.4% | 4361.79 | 457987.50 | 23.48 | 5.46 | 1.06 |
| HA vs prior-opposed | ha_with_fade | 327 | 64.2% | 2669.52 | 872932.50 | 13.61 | -1.75 | -0.50 |
| HA vs implied ST | ha_confirms_st | 105 | 71.4% | 4361.79 | 457987.50 | 23.48 | 5.46 | 1.06 |
| HA vs implied ST | ha_fades_st | 327 | 64.2% | 2669.52 | 872932.50 | 13.61 | -1.75 | -0.50 |
| HA color | ha_bear | 231 | 67.5% | 2829.95 | 653717.50 | 16.19 | 1.56 | 0.40 |
| HA color | ha_bull | 201 | 64.2% | 3369.17 | 677202.50 | 18.67 | -1.79 | -0.44 |
| HA streak | streak_1_2 | 176 | 69.3% | 4012.56 | 706210.00 | 19.28 | 3.35 | 0.79 |
| HA streak | streak_ge7 | 67 | 65.7% | 1728.17 | 115787.50 | 4.02 | -0.30 | -0.05 |
| HA streak | streak_3_6 | 189 | 63.0% | 2692.71 | 508922.50 | 6.13 | -3.01 | -0.73 |

Read: fade n=327 WR=64.2% avg=$2670 vs trend-HA n=105 WR=71.4% avg=$4362. HA-with-prior-trend looks **better** than HA-with-fade (fade is fighting HA).

### HA × current HP conditions (n≥40)

| ha_vs_po | current_condition | current_bucket | n | wr | avg_net | ns | z_wr |
|---|---|---|---:|---:|---:|---:|---:|
| ha_with_prior_trend | Hourly RSI vs trade | rsi_against_side | 78 | 75.6% | 4550 | 18.19 | 1.66 |
| ha_with_prior_trend | 5m MA vs trade | ma_opposed | 61 | 73.8% | 5450 | 23.44 | 1.20 |
| ha_with_prior_trend | ST-event age | st_age_lt30m | 70 | 72.9% | 3210 | 11.52 | 1.13 |
| ha_with_prior_trend | Opening 15m direction vs trade | or_aligned | 59 | 72.9% | 4482 | 13.55 | 1.05 |
| ha_with_fade | Opening 15m range vs ATR | or_norm | 92 | 70.7% | 4288 | 16.49 | 0.86 |
| ha_with_fade | ST-event age | st_age_30_90m | 95 | 70.5% | 3482 | 13.65 | 0.85 |
| ha_with_fade | Hourly RSI vs trade | rsi_against_side | 170 | 68.8% | 3988 | 29.68 | 0.66 |
| ha_with_prior_trend | Opening 15m direction vs trade | or_opposed | 46 | 69.6% | 4208 | 6.22 | 0.49 |
| ha_with_fade | Overnight range third | on_lower | 129 | 67.4% | 3165 | 12.88 | 0.31 |
| ha_with_prior_trend | 5m MA vs trade | ma_aligned | 44 | 68.2% | 2853 | 4.70 | 0.29 |
| ha_with_fade | Overnight range third | on_middle | 71 | 67.6% | 3692 | 8.47 | 0.27 |
| ha_with_fade | Opening 15m direction vs trade | or_opposed | 141 | 66.0% | 2622 | 7.29 | -0.00 |
| ha_with_fade | 5m MA vs trade | ma_aligned | 230 | 65.2% | 2792 | 13.10 | -0.20 |
| ha_with_fade | ST-event age | st_age_gt180m | 62 | 64.5% | 2525 | 4.48 | -0.23 |
| ha_with_fade | Opening 15m range vs ATR | or_narrow | 96 | 63.5% | 1453 | 6.50 | -0.45 |

## ym_prior_opposed_rl

Baseline n=436 WR=61.0% net=$289225 N/S=9.74

### HA vs PO / ST

| condition | bucket | n | wr | avg_net | net | ns | wr_lift_pp | z_wr |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| HA vs prior-opposed | ha_with_fade | 381 | 61.9% | 751.42 | 286292.50 | 9.64 | 0.93 | 0.27 |
| HA vs prior-opposed | ha_with_prior_trend | 55 | 54.5% | 53.32 | 2932.50 | 0.17 | -6.46 | -0.93 |
| HA vs implied ST | ha_fades_st | 381 | 61.9% | 751.42 | 286292.50 | 9.64 | 0.93 | 0.27 |
| HA vs implied ST | ha_confirms_st | 55 | 54.5% | 53.32 | 2932.50 | 0.17 | -6.46 | -0.93 |
| HA color | ha_bull | 202 | 62.4% | 924.85 | 186818.75 | 7.53 | 1.37 | 0.33 |
| HA color | ha_bear | 234 | 59.8% | 437.63 | 102406.25 | 3.53 | -1.18 | -0.30 |
| HA streak | streak_1_2 | 170 | 64.7% | 460.99 | 78367.50 | 2.41 | 3.70 | 0.84 |
| HA streak | streak_3_6 | 184 | 60.9% | 907.57 | 166993.75 | 7.18 | -0.14 | -0.03 |
| HA streak | streak_ge7 | 82 | 53.7% | 534.92 | 43863.75 | 2.21 | -7.35 | -1.25 |

Read: fade n=381 WR=61.9% avg=$751 vs trend-HA n=55 WR=54.5% avg=$53. HA-with-fade looks **better** than HA-with-prior-trend.

### HA × current HP conditions (n≥40)

| ha_vs_po | current_condition | current_bucket | n | wr | avg_net | ns | z_wr |
|---|---|---|---:|---:|---:|---:|---:|
| ha_with_fade | Overnight range third | on_middle | 94 | 73.4% | 1205 | 13.71 | 2.23 |
| ha_with_fade | Hourly RSI vs trade | rsi_against_side | 205 | 67.8% | 984 | 13.17 | 1.65 |
| ha_with_fade | 5m MA vs trade | ma_opposed | 120 | 67.5% | 829 | 4.12 | 1.29 |
| ha_with_fade | ST-event age | st_age_30_90m | 90 | 65.6% | 1246 | 8.37 | 0.81 |
| ha_with_fade | Opening 15m direction vs trade | or_opposed | 159 | 64.2% | 1107 | 6.93 | 0.70 |
| ha_with_fade | ST-event age | st_age_lt30m | 167 | 63.5% | 477 | 2.41 | 0.56 |
| ha_with_fade | Opening 15m range vs ATR | or_narrow | 102 | 63.7% | 666 | 4.44 | 0.51 |
| ha_with_fade | Opening 15m range vs ATR | or_norm | 110 | 63.6% | 629 | 4.00 | 0.50 |
| ha_with_fade | ST-event age | st_age_90_180m | 55 | 63.6% | 974 | 4.44 | 0.38 |
| ha_with_fade | Opening 15m direction vs trade | or_aligned | 222 | 60.4% | 497 | 4.49 | -0.16 |
| ha_with_fade | Opening 15m range vs ATR | or_wide | 169 | 59.8% | 883 | 4.61 | -0.28 |
| ha_with_fade | 5m MA vs trade | ma_aligned | 261 | 59.4% | 716 | 8.71 | -0.42 |
| ha_with_fade | Hourly RSI vs trade | rsi_neutral | 109 | 58.7% | 758 | 4.69 | -0.44 |
| ha_with_fade | Overnight range third | on_upper | 146 | 58.9% | 645 | 3.85 | -0.45 |
| ha_with_fade | Overnight range third | on_lower | 141 | 57.4% | 559 | 3.61 | -0.75 |

## Post-exit 3R (after PO campaign)

First 5m close after PO exit; SL at that candle open; TP 3× body; flatten 16:00. Skip if exit ≥ 15:30. Conservative same-bar: stop before target.

| Sleeve | n | WR | avg | net | N/S | PF-proxy |
|---|---:|---:|---:|---:|---:|---:|
| countertrend_again_po | 171 | 18.1% | $17 | $2894 | 0.32 | 1.09 |
| follow_ha_at_entry | 171 | 21.1% | $-4 | $-756 | -0.09 | 0.97 |
| trend_continuation_st | 183 | 21.9% | $-60 | $-10990 | -0.76 | 0.64 |

### By book

| Book | Sleeve | n | WR | net | N/S |
|---|---|---:|---:|---:|---:|
| nq_prior_opposed_rl | countertrend_again_po | 93 | 19.4% | $5706 | 0.74 |
| nq_prior_opposed_rl | follow_ha_at_entry | 88 | 19.3% | $353 | 0.04 |
| nq_prior_opposed_rl | trend_continuation_st | 84 | 16.7% | $-11691 | -0.88 |
| ym_prior_opposed_rl | countertrend_again_po | 78 | 16.7% | $-2812 | -0.73 |
| ym_prior_opposed_rl | follow_ha_at_entry | 83 | 22.9% | $-1110 | -0.46 |
| ym_prior_opposed_rl | trend_continuation_st | 99 | 26.3% | $702 | 0.33 |

## Stance

Research curiosity only. Do **not** promote an HA filter from this pass. Compare HA lift to the already-shortlisted HP buckets (NQ OR-norm is the live HP candidate). Post-exit 3R is a separate satellite idea — needs nulls before any size.

Hub: `/home/tester/hsm/potions/live/state/prior_opposed_ha`

