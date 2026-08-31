# ES quarterly range breakout — HP + HTF condition profile

Study: `es_quarterly_breakout_hp_v1`
Hub: `live/state/es_quarterly_breakout_hp_profile/`
Tape: `es_quarterly_range_breakout_broker` (Engine + PaperBroker, daily).

## Baseline

| n | WR | net | stress | N/S | avg |
|---:|---:|---:|---:|---:|---:|
| 60 | 71.7% | +1258368 | 154216 | 8.16 | +20973 |

## Shortlist / HTF null candidates

| source | condition=bucket | n | cov | WR lift | avg lift | inc N/S |
|---|---|---:|---:|---:|---:|---:|
| shortlist | Week of month=3 | 13 | 22% | +20.6pp | +18892 | 26.03 |
| shortlist | Monthly OR direction=mor_up | 26 | 43% | +12.9pp | +10933 | 8.36 |
| shortlist | Prior RTH range percentile=prior_range_norm | 22 | 37% | +19.2pp | +5912 | 7.20 |
| shortlist | ATR14 quartile=atr_q4 | 15 | 25% | +1.7pp | +23365 | 3.97 |
| htf_forced | Yearly ORB direction=yor_up | 33 | 55% | +4.1pp | +1371 | 6.69 |
| htf_forced | Weekly ATR trend vs trade=w_atr_aligned | 49 | 82% | +1.8pp | +690 | 5.01 |

## HTF bucket lifts

| condition=bucket | n | cov | WR lift | avg lift | inc N/S |
|---|---:|---:|---:|---:|---:|
| Monthly OR direction=mor_up | 26 | 43% | +12.9pp | +10933 | 8.36 |
| Monthly OR direction=mor_na | 16 | 27% | -9.2pp | +1402 | 3.00 |
| Monthly OR direction=mor_down | 11 | 18% | -26.2pp | -32801 | -0.56 |
| Prior quarter type=q_break_up | 42 | 70% | -2.6pp | -5598 | 6.51 |
| Weekly ATR trend vs trade=w_atr_aligned | 49 | 82% | +1.8pp | +690 | 5.01 |
| Weekly ATR trend vs trade=w_atr_opposed | 11 | 18% | -8.0pp | -3073 | 6.11 |
| Yearly ORB direction=yor_up | 33 | 55% | +4.1pp | +1371 | 6.69 |
| Yearly ORB direction=yor_na | 19 | 32% | -8.5pp | -11147 | 1.63 |

## Notables (dual-lift heuristic)

| condition=bucket | n | WR lift | avg lift | z_WR |
|---|---:|---:|---:|---:|
| Day of week=Monday | 12 | +20.0pp | +11656 | 1.40 |
| Day of week=Thursday | 12 | +20.0pp | +20009 | 1.40 |
| Week of month=3 | 13 | +20.6pp | +18892 | 1.50 |
| ATR14 quartile=atr_q4 | 15 | +1.7pp | +23365 | 0.13 |
| Prior RTH close location=prior_close_low_third | 13 | +12.9pp | +11631 | 0.94 |
| Prior RTH range percentile=prior_range_norm | 22 | +19.2pp | +5912 | 1.71 |
| Monthly OR direction=mor_up | 26 | +12.9pp | +10933 | 1.22 |

## Stance (profile only)

Diagnostic. Null suite @ 1.25× decides validation. Does **not** rewrite futures LIVE_PLAN.
Null pairs: 9 → `live/state/es_quarterly_breakout_hp_nulls/`
