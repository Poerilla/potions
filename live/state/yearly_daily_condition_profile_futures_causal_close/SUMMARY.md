# Yearly / daily HP condition profile

Diagnostic only — multi-month hold books on **daily** causal features.
Min bucket N=12. Notable = dual WR+avg lift and (|z_WR|≥1.28 or avg lift ≥35% of |baseline avg|).
Hold-duration buckets are outcome-correlated; shown but excluded from notables.

## Books

| Book | Family | n | WR | Avg $ | Net $ | fills |
|---|---|---:|---:|---:|---:|---|
| NQ Yearly ORB L_4_1_1 causal close | yearly_orb | 68 | 29.4% | $11,243 | $764,503 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_futures_causal_close/states/nq_yorb_sizing_L_4_1_1/fills.csv` |
| ES Yearly ORB L_4_2_1 causal close | yearly_orb | 73 | 20.5% | $937 | $68,396 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_futures_causal_close/states/es_yorb_sizing_L_4_2_1/fills.csv` |
| YM Yearly ORB L_4_1_1 causal close | yearly_orb | 81 | 22.2% | $1,948 | $157,766 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_futures_causal_close/states/ym_yorb_sizing_L_4_1_1/fills.csv` |

## Cross-book notables

| condition | bucket | books | mean WR lift | mean avg lift |
|---|---|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 3 | +16.5pp | $+6,260 |
| dow | Monday | 1 | +11.1pp | $+4,385 |
| dow | Sunday | 2 | +12.9pp | $+2,725 |
| dow | Wednesday | 1 | +10.2pp | $+1,078 |
| entry_month | August | 1 | +8.5pp | $+3,618 |
| entry_month | June | 1 | +12.3pp | $+12,781 |
| ma_align | ma_aligned | 1 | +0.4pp | $+1,437 |
| ma_align | ma_mixed | 2 | +10.2pp | $+6,919 |
| ma_stack | ma_mixed | 2 | +10.2pp | $+6,919 |
| or_width_bucket | or_mid | 1 | +0.9pp | $+2,356 |
| or_width_bucket | or_wide | 2 | +5.4pp | $+13,984 |
| prior_year_loc | prior_yr_upper | 2 | +4.6pp | $+1,054 |
| prior_year_ret_bucket | prior_yr_mid | 1 | +17.8pp | $+7,447 |
| prior_year_ret_bucket | prior_yr_strong | 2 | +6.4pp | $+5,064 |
| quarter | Q3 | 1 | +11.1pp | $+3,041 |
| quarter | Q4 | 1 | +11.0pp | $+2,040 |
| rsi_align | rsi_against_side | 1 | +17.9pp | $+12,081 |
| rsi_align | rsi_neutral | 1 | +8.7pp | $+5,786 |
| rsi_align | rsi_with_side | 1 | +1.6pp | $+1,856 |
| rsi_bucket | rsi_45_55 | 1 | +8.7pp | $+5,786 |
| side | short | 1 | +19.0pp | $+200 |
| week_of_month | 2 | 3 | +7.3pp | $+6,774 |

## Per-book top positive buckets

### NQ Yearly ORB L_4_1_1 causal close

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| week_of_month | 2 | 22 | 45.5% | +16.0pp | $24,315 | $+13,072 | 10.61 | +1.44 |
| entry_month | June | 12 | 41.7% | +12.3pp | $24,024 | $+12,781 | 8.03 | +0.86 |
| atr_pct_bucket | atr_pctl_q4 | 24 | 41.7% | +12.3pp | $19,023 | $+7,780 | 4.93 | +1.13 |
| or_width_bucket | or_wide | 20 | 40.0% | +10.6pp | $35,492 | $+24,249 | 5.52 | +0.91 |
| prior_year_ret_bucket | prior_yr_strong | 18 | 38.9% | +9.5pp | $16,764 | $+5,522 | 3.31 | +0.78 |
| rsi_bucket | rsi_45_55 | 21 | 38.1% | +8.7pp | $17,029 | $+5,786 | 4.94 | +0.76 |
| rsi_align | rsi_neutral | 21 | 38.1% | +8.7pp | $17,029 | $+5,786 | 4.94 | +0.76 |
| ma_align | ma_mixed | 18 | 33.3% | +3.9pp | $16,859 | $+5,616 | 2.88 | +0.32 |
| ma_stack | ma_mixed | 18 | 33.3% | +3.9pp | $16,859 | $+5,616 | 2.88 | +0.32 |

### ES Yearly ORB L_4_2_1 causal close

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| rsi_align | rsi_against_side | 13 | 38.5% | +17.9pp | $13,018 | $+12,081 | 2.76 | +1.47 |
| ma_align | ma_mixed | 27 | 37.0% | +16.5pp | $9,158 | $+8,222 | 2.71 | +1.81 |
| ma_stack | ma_mixed | 27 | 37.0% | +16.5pp | $9,158 | $+8,222 | 2.71 | +1.81 |
| dow | Sunday | 12 | 33.3% | +12.8pp | $2,201 | $+1,264 | 1.54 | +1.02 |
| quarter | Q4 | 19 | 31.6% | +11.0pp | $2,977 | $+2,040 | 1.91 | +1.06 |
| dow | Wednesday | 13 | 30.8% | +10.2pp | $2,014 | $+1,078 | 1.29 | +0.84 |
| atr_pct_bucket | atr_pctl_q4 | 22 | 27.3% | +6.7pp | $8,199 | $+7,262 | 2.47 | +0.68 |
| prior_year_ret_bucket | prior_yr_strong | 21 | 23.8% | +3.3pp | $5,544 | $+4,607 | 1.68 | +0.33 |
| week_of_month | 2 | 17 | 23.5% | +3.0pp | $5,517 | $+4,580 | 2.29 | +0.27 |
| prior_year_loc | prior_yr_upper | 56 | 23.2% | +2.7pp | $1,652 | $+715 | 1.32 | +0.37 |
| or_width_bucket | or_wide | 24 | 20.8% | +0.3pp | $4,656 | $+3,719 | 1.50 | +0.03 |

### YM Yearly ORB L_4_1_1 causal close

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 19 | 52.6% | +30.4pp | $5,685 | $+3,737 | 3.16 | +2.87 |
| side | short | 17 | 41.2% | +19.0pp | $2,148 | $+200 | 1.57 | +1.71 |
| prior_year_ret_bucket | prior_yr_mid | 20 | 40.0% | +17.8pp | $9,395 | $+7,447 | 8.04 | +1.71 |
| dow | Sunday | 17 | 35.3% | +13.1pp | $6,134 | $+4,186 | 5.82 | +1.18 |
| dow | Monday | 12 | 33.3% | +11.1pp | $6,332 | $+4,385 | 4.89 | +0.86 |
| quarter | Q3 | 30 | 33.3% | +11.1pp | $4,988 | $+3,041 | 3.84 | +1.25 |
| entry_month | August | 13 | 30.8% | +8.5pp | $5,566 | $+3,618 | 4.96 | +0.69 |
| prior_year_loc | prior_yr_upper | 59 | 28.8% | +6.6pp | $3,341 | $+1,393 | 2.49 | +0.93 |
| week_of_month | 2 | 20 | 25.0% | +2.8pp | $4,617 | $+2,669 | 4.91 | +0.27 |
| rsi_align | rsi_with_side | 42 | 23.8% | +1.6pp | $3,804 | $+1,856 | 3.05 | +0.20 |
| or_width_bucket | or_mid | 26 | 23.1% | +0.9pp | $4,304 | $+2,356 | 3.69 | +0.09 |
| ma_align | ma_aligned | 53 | 22.6% | +0.4pp | $3,384 | $+1,437 | 2.67 | +0.06 |

## Caveats

- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.
- Yearly ORB sample is sparse (~1–4 campaigns/year); prefer signals that repeat across books.
- Follow with null/OOS / broker-like filter tests before any size-up or sit-out.

