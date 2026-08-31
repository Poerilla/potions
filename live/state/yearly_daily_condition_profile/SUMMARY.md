# Yearly / daily HP condition profile

Diagnostic only — multi-month hold books on **daily** causal features.
Min bucket N=12. Notable = dual WR+avg lift and (|z_WR|≥1.28 or avg lift ≥35% of |baseline avg|).
Hold-duration buckets are outcome-correlated; shown but excluded from notables.

## Books

| Book | Family | n | WR | Avg $ | Net $ | fills |
|---|---|---:|---:|---:|---:|---|
| AUDJPY Yearly ORB L_4_1_1 (sizing best) | yearly_orb | 146 | 90.4% | $2,878 | $420,156 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_fx_metals/states/audjpy_yorb_sizing_L_4_1_1/fills.csv` |
| XAUUSD Yearly ORB L_4_2_1 (sizing best) | yearly_orb | 91 | 94.5% | $11,403 | $1,037,711 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_fx_metals/states/xauusd_yorb_sizing_L_4_2_1/fills.csv` |
| XAGUSD Yearly ORB L_5_2_1 (sizing best) | yearly_orb | 89 | 89.9% | $3,386 | $301,376 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_fx_metals/states/xagusd_yorb_sizing_L_5_2_1/fills.csv` |
| NQ Yearly ORB L_4_1_1 (sizing best) | yearly_orb | 68 | 86.8% | $20,844 | $1,417,383 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep/states/nq_yorb_sizing_L_4_1_1/fills.csv` |
| ES Yearly ORB L_4_2_1 (sizing best) | yearly_orb | 73 | 76.7% | $9,002 | $657,146 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_micro/states/es_yorb_sizing_L_4_2_1/fills.csv` |
| YM Yearly ORB L_4_1_1 (sizing best) | yearly_orb | 81 | 90.1% | $6,367 | $515,736 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_micro/states/ym_yorb_sizing_L_4_1_1/fills.csv` |
| NQ ATR daily ladder 1/1/2/2/2/1 10-max intv2 | atr_st | 149 | 13.4% | $10,551 | $1,572,142 | `/home/tester/hsm/potions/live/state/atr_sizing_sweep/states/nq_atr_sizing_daily_ladder112221_10max_intv2/fills.csv` |
| MNQ ATR daily ladder 1/1/2/2/2/1 10-max intv2 | atr_st | 52 | 21.2% | $2,825 | $146,875 | `/home/tester/hsm/potions/live/state/atr_sizing_sweep/states/mnq_atr_sizing_daily_ladder112221_10max_intv2/fills.csv` |
| XAUUSD ATR daily ladder 1/1/2/2/2 10-max | atr_st | 200 | 11.5% | $2,806 | $561,150 | `/home/tester/hsm/potions/live/state/metals_futures_strats_sweep/states/xauusd_atr_daily_ladder112221_10max/fills.csv` |

## Cross-book notables

| condition | bucket | books | mean WR lift | mean avg lift |
|---|---|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q2 | 1 | +0.1pp | $+3,611 |
| atr_pct_bucket | atr_pctl_q3 | 1 | +0.1pp | $+2,632 |
| atr_pct_bucket | atr_pctl_q4 | 6 | +8.7pp | $+9,174 |
| dow | Monday | 2 | +3.2pp | $+5,070 |
| dow | Saturday | 2 | +2.9pp | $+4,176 |
| dow | Thursday | 1 | +4.0pp | $+21,857 |
| dow | Wednesday | 1 | +7.9pp | $+3,327 |
| entry_month | April | 1 | +1.8pp | $+3,043 |
| entry_month | August | 1 | +3.9pp | $+10,379 |
| entry_month | July | 1 | +10.1pp | $+2,114 |
| entry_month | May | 1 | +0.7pp | $+6,071 |
| entry_month | October | 1 | +28.2pp | $+2,321 |
| ma_align | ma_aligned | 1 | +3.2pp | $+3,456 |
| ma_align | ma_mixed | 3 | +9.6pp | $+8,419 |
| ma_stack | ma_bull_stack | 2 | +3.4pp | $+3,144 |
| ma_stack | ma_mixed | 3 | +9.6pp | $+8,419 |
| or_ext_bucket | ext_25_75 | 1 | +12.7pp | $+8,894 |
| or_ext_bucket | ext_75_150 | 1 | +11.6pp | $+422 |
| or_ext_bucket | ext_gt150 | 1 | +13.5pp | $+212 |
| or_width_bucket | or_wide | 5 | +5.3pp | $+13,317 |
| prior_year_loc | prior_yr_lower | 2 | +9.9pp | $+17,570 |
| prior_year_loc | prior_yr_upper | 3 | +1.2pp | $+3,058 |
| prior_year_ret_bucket | prior_yr_mid | 1 | +0.3pp | $+1,730 |
| prior_year_ret_bucket | prior_yr_strong | 5 | +3.1pp | $+4,625 |
| quarter | Q2 | 1 | +3.2pp | $+19,689 |
| quarter | Q3 | 1 | +2.5pp | $+4,037 |
| quarter | Q4 | 1 | +9.6pp | $+1,067 |
| rsi_align | rsi_against_side | 1 | +15.6pp | $+15,170 |
| rsi_align | rsi_neutral | 1 | +9.6pp | $+10 |
| rsi_bucket | rsi_30_45 | 1 | +4.3pp | $+2,888 |
| rsi_bucket | rsi_45_55 | 1 | +9.6pp | $+10 |
| rsi_bucket | rsi_le30 | 1 | +2.4pp | $+1,326 |
| side | long | 1 | +0.8pp | $+1,962 |
| side | short | 2 | +14.0pp | $+4,605 |
| week_of_month | 1 | 2 | +2.9pp | $+2,052 |
| week_of_month | 2 | 1 | +0.9pp | $+5,661 |
| week_of_month | 4 | 2 | +7.7pp | $+3,555 |
| week_of_month | 5 | 1 | +7.2pp | $+7,728 |
| ytd_bucket | ytd_up15p | 2 | +6.1pp | $+2,890 |
| ytd_bucket | ytd_up5_15 | 1 | +3.3pp | $+4,759 |

## Per-book top positive buckets

### AUDJPY Yearly ORB L_4_1_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| quarter | Q4 | 32 | 100.0% | +9.6pp | $3,945 | $+1,067 | 99.00 | +1.67 |
| rsi_bucket | rsi_45_55 | 37 | 100.0% | +9.6pp | $2,888 | $+10 | 99.00 | +1.77 |
| rsi_align | rsi_neutral | 37 | 100.0% | +9.6pp | $2,888 | $+10 | 99.00 | +1.77 |
| week_of_month | 1 | 35 | 94.3% | +3.9pp | $3,897 | $+1,019 | 28.81 | +0.70 |
| ma_align | ma_mixed | 48 | 93.8% | +3.3pp | $3,953 | $+1,075 | 47.61 | +0.68 |
| ma_stack | ma_mixed | 48 | 93.8% | +3.3pp | $3,953 | $+1,075 | 47.61 | +0.68 |
| rsi_bucket | rsi_le30 | 14 | 92.9% | +2.4pp | $4,204 | $+1,326 | 190.06 | +0.30 |

### XAUUSD Yearly ORB L_4_2_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 25 | 100.0% | +5.5pp | $22,366 | $+10,962 | 99.00 | +1.07 |
| prior_year_ret_bucket | prior_yr_strong | 29 | 96.6% | +2.0pp | $17,213 | $+5,810 | 14.88 | +0.42 |
| entry_month | May | 21 | 95.2% | +0.7pp | $17,474 | $+6,071 | 30.23 | +0.13 |
| prior_year_loc | prior_yr_upper | 39 | 94.9% | +0.4pp | $17,131 | $+5,727 | 15.91 | +0.08 |

### XAGUSD Yearly ORB L_5_2_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| entry_month | July | 12 | 100.0% | +10.1pp | $5,501 | $+2,114 | 99.00 | +1.09 |
| ma_stack | ma_bull_stack | 31 | 93.5% | +3.7pp | $6,218 | $+2,832 | 36.33 | +0.58 |
| prior_year_ret_bucket | prior_yr_strong | 29 | 93.1% | +3.2pp | $5,002 | $+1,616 | 313.65 | +0.50 |
| or_width_bucket | or_wide | 28 | 92.9% | +3.0pp | $4,750 | $+1,364 | 1188.46 | +0.45 |
| entry_month | April | 12 | 91.7% | +1.8pp | $6,429 | $+3,043 | 92.41 | +0.19 |
| side | long | 43 | 90.7% | +0.8pp | $5,349 | $+1,962 | 39.18 | +0.14 |
| atr_pct_bucket | atr_pctl_q3 | 20 | 90.0% | +0.1pp | $6,018 | $+2,632 | 20.41 | +0.02 |
| prior_year_loc | prior_yr_upper | 40 | 90.0% | +0.1pp | $4,768 | $+1,382 | 46.15 | +0.02 |

### NQ Yearly ORB L_4_1_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ma_align | ma_mixed | 18 | 100.0% | +13.2pp | $36,240 | $+15,396 | 99.00 | +1.47 |
| ma_stack | ma_mixed | 18 | 100.0% | +13.2pp | $36,240 | $+15,396 | 99.00 | +1.47 |
| atr_pct_bucket | atr_pctl_q4 | 24 | 95.8% | +9.1pp | $32,188 | $+11,344 | 26.90 | +1.13 |
| or_width_bucket | or_wide | 20 | 95.0% | +8.2pp | $53,733 | $+32,889 | 37.03 | +0.96 |
| prior_year_ret_bucket | prior_yr_strong | 18 | 88.9% | +2.1pp | $30,660 | $+9,816 | 17.30 | +0.24 |

### ES Yearly ORB L_4_2_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 22 | 95.5% | +18.7pp | $23,255 | $+14,253 | 68.11 | +1.82 |
| side | short | 19 | 94.7% | +18.0pp | $14,742 | $+5,740 | 12.98 | +1.66 |
| rsi_align | rsi_against_side | 13 | 92.3% | +15.6pp | $24,172 | $+15,170 | 14.44 | +1.23 |
| ma_align | ma_mixed | 27 | 88.9% | +12.2pp | $17,789 | $+8,787 | 17.13 | +1.28 |
| ma_stack | ma_mixed | 27 | 88.9% | +12.2pp | $17,789 | $+8,787 | 17.13 | +1.28 |
| week_of_month | 4 | 17 | 88.2% | +11.5pp | $12,636 | $+3,634 | 10.43 | +1.01 |
| dow | Wednesday | 13 | 84.6% | +7.9pp | $12,329 | $+3,327 | 9.03 | +0.62 |
| prior_year_loc | prior_yr_lower | 12 | 83.3% | +6.6pp | $13,704 | $+4,702 | 16.63 | +0.50 |
| or_width_bucket | or_wide | 24 | 79.2% | +2.5pp | $20,388 | $+11,386 | 7.70 | +0.25 |

### YM Yearly ORB L_4_1_1 (sizing best)

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| side | short | 17 | 100.0% | +9.9pp | $9,838 | $+3,471 | 99.00 | +1.24 |
| atr_pct_bucket | atr_pctl_q4 | 19 | 94.7% | +4.6pp | $11,431 | $+5,064 | 42.30 | +0.61 |
| rsi_bucket | rsi_30_45 | 18 | 94.4% | +4.3pp | $9,255 | $+2,888 | 32.68 | +0.56 |
| dow | Monday | 12 | 91.7% | +1.5pp | $9,537 | $+3,170 | 22.28 | +0.17 |

### NQ ATR daily ladder 1/1/2/2/2/1 10-max intv2

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| entry_month | October | 12 | 41.7% | +28.2pp | $12,873 | $+2,321 | 6.19 | +2.76 |
| prior_year_loc | prior_yr_lower | 15 | 26.7% | +13.2pp | $40,989 | $+30,438 | 9.28 | +1.43 |
| or_ext_bucket | ext_25_75 | 23 | 26.1% | +12.7pp | $19,445 | $+8,894 | 6.98 | +1.66 |
| or_ext_bucket | ext_75_150 | 20 | 25.0% | +11.6pp | $10,973 | $+422 | 5.88 | +1.43 |
| or_width_bucket | or_wide | 47 | 21.3% | +7.9pp | $27,710 | $+17,158 | 5.11 | +1.38 |
| ytd_bucket | ytd_up15p | 39 | 20.5% | +7.1pp | $14,825 | $+4,274 | 9.12 | +1.16 |
| dow | Monday | 22 | 18.2% | +4.8pp | $17,520 | $+6,969 | 6.33 | +0.61 |
| prior_year_ret_bucket | prior_yr_strong | 44 | 18.2% | +4.8pp | $15,361 | $+4,810 | 3.77 | +0.81 |
| dow | Thursday | 23 | 17.4% | +4.0pp | $32,408 | $+21,857 | 13.27 | +0.52 |
| quarter | Q2 | 30 | 16.7% | +3.2pp | $30,240 | $+19,689 | 12.02 | +0.48 |
| dow | Saturday | 31 | 16.1% | +2.7pp | $15,901 | $+5,349 | 6.08 | +0.40 |
| atr_pct_bucket | atr_pctl_q4 | 52 | 15.4% | +2.0pp | $21,049 | $+10,498 | 8.13 | +0.36 |

### MNQ ATR daily ladder 1/1/2/2/2/1 10-max intv2

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 18 | 33.3% | +12.2pp | $5,749 | $+2,924 | 13.78 | +1.09 |
| week_of_month | 4 | 12 | 25.0% | +3.8pp | $6,301 | $+3,477 | 10.71 | +0.29 |

### XAUUSD ATR daily ladder 1/1/2/2/2 10-max

| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| or_ext_bucket | ext_gt150 | 12 | 25.0% | +13.5pp | $3,018 | $+212 | 2.46 | +1.42 |
| week_of_month | 5 | 16 | 18.8% | +7.2pp | $10,533 | $+7,728 | 7.81 | +0.87 |
| ytd_bucket | ytd_up15p | 30 | 16.7% | +5.2pp | $4,312 | $+1,506 | 2.05 | +0.83 |
| or_width_bucket | or_wide | 61 | 16.4% | +4.9pp | $6,593 | $+3,787 | 2.66 | +1.05 |
| entry_month | August | 26 | 15.4% | +3.9pp | $13,185 | $+10,379 | 6.74 | +0.58 |
| ytd_bucket | ytd_up5_15 | 54 | 14.8% | +3.3pp | $7,564 | $+4,759 | 7.70 | +0.68 |
| prior_year_ret_bucket | prior_yr_strong | 61 | 14.8% | +3.3pp | $3,877 | $+1,071 | 2.32 | +0.70 |
| ma_align | ma_aligned | 109 | 14.7% | +3.2pp | $6,261 | $+3,456 | 3.82 | +0.84 |
| ma_stack | ma_bull_stack | 109 | 14.7% | +3.2pp | $6,261 | $+3,456 | 3.82 | +0.84 |
| dow | Saturday | 41 | 14.6% | +3.1pp | $5,809 | $+3,003 | 3.23 | +0.57 |
| prior_year_loc | prior_yr_upper | 96 | 14.6% | +3.1pp | $4,872 | $+2,066 | 2.96 | +0.78 |
| quarter | Q3 | 57 | 14.0% | +2.5pp | $6,843 | $+4,037 | 4.91 | +0.53 |

## Caveats

- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.
- Yearly ORB sample is sparse (~1–4 campaigns/year); prefer signals that repeat across books.
- Follow with null/OOS / broker-like filter tests before any size-up or sit-out.

