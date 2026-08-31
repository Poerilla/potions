# ES quarterly breakout — HP + HTF study

Hubs:
- Profile: `live/state/es_quarterly_breakout_hp_profile/`
- Nulls @1.25×: `live/state/es_quarterly_breakout_hp_nulls/` (LIVE_PLAN not rewritten)

Book: `es_quarterly_range_breakout` (n=60, net=+1258368, path N/S=8.16, tracker N/S=5.59).

## Stance

**NOT VALIDATED**

## Null decisions @1.25×

| decision | condition=bucket | hp% | ΔN/S | p_master |
|---|---|---:|---:|---:|
| NOT VALIDATED | Week of month=3 | 21.7 | +1.05 | 0.513 |
| NOT VALIDATED | Monthly OR direction=mor_up | 43.3 | +1.34 | 0.255 |
| NOT VALIDATED | Prior RTH range percentile=prior_range_norm | 36.7 | +0.96 | 0.699 |
| NOT VALIDATED | ATR14 quartile=atr_q4 | 25.0 | -0.89 | 1.000 |
| NOT VALIDATED | Yearly ORB direction=yor_up | 55.0 | +0.15 | 1.000 |
| NOT VALIDATED | Weekly ATR trend vs trade=w_atr_aligned | 81.7 | -0.81 | 1.000 |
| NOT VALIDATED | Monthly OR direction=mor_down | 18.3 | -1.66 | 1.000 |
| NOT VALIDATED | Prior quarter type=q_break_up | 70.0 | +1.00 | 0.635 |
| NOT VALIDATED | Weekly ATR trend vs trade=w_atr_opposed | 18.3 | +0.51 | 0.994 |

## HTF diagnostics

| condition=bucket | n | cov | WR lift | avg lift |
|---|---:|---:|---:|---:|
| Monthly OR direction=mor_up | 26 | 43% | +12.9pp | +10933 |
| Monthly OR direction=mor_na | 16 | 27% | -9.2pp | +1402 |
| Monthly OR direction=mor_down | 11 | 18% | -26.2pp | -32801 |
| Prior quarter type=q_break_up | 42 | 70% | -2.6pp | -5598 |
| Weekly ATR trend vs trade=w_atr_aligned | 49 | 82% | +1.8pp | +690 |
| Weekly ATR trend vs trade=w_atr_opposed | 11 | 18% | -8.0pp | -3073 |
| Yearly ORB direction=yor_up | 33 | 55% | +4.1pp | +1371 |
| Yearly ORB direction=yor_na | 19 | 32% | -8.5pp | -11147 |

## Coverage-band / forced shortlist

| source | condition=bucket | n | avg lift | inc N/S |
|---|---|---:|---:|---:|
| shortlist | Week of month=3 | 13 | +18892 | 26.03 |
| shortlist | Monthly OR direction=mor_up | 26 | +10933 | 8.36 |
| shortlist | Prior RTH range percentile=prior_range_norm | 22 | +5912 | 7.20 |
| shortlist | ATR14 quartile=atr_q4 | 15 | +23365 | 3.97 |
| htf_forced | Yearly ORB direction=yor_up | 33 | +1371 | 6.69 |
| htf_forced | Weekly ATR trend vs trade=w_atr_aligned | 49 | +690 | 5.01 |

## Takeaway

Quarterly breakout remains a strong **baseline** book (tracker N/S 5.59).
HP size-up needs null-suite pass on ΔN/S. HTF regime tags are often wide-coverage
and may stay diagnostic even when WR lifts in-sample.

Definitions: `HTF_FEATURES.md`.
