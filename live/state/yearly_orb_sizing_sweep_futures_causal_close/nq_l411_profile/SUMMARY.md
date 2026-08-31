# Yearly / daily HP condition profile

Diagnostic only — multi-month hold books on **daily** causal features.
Min bucket N=12. Notable = dual WR+avg lift and (|z_WR|≥1.28 or avg lift ≥35% of |baseline avg|).
Hold-duration buckets are outcome-correlated; shown but excluded from notables.

## Books

| Book | Family | n | WR | Avg $ | Net $ | fills |
|---|---|---:|---:|---:|---:|---|
| NQ Yearly ORB L_4_1_1 causal close | yearly_orb | 68 | 29.4% | $11,243 | $764,503 | `/home/tester/hsm/potions/live/state/yearly_orb_sizing_sweep_futures_causal_close/states/nq_yorb_sizing_L_4_1_1/fills.csv` |

## Cross-book notables

| condition | bucket | books | mean WR lift | mean avg lift |
|---|---|---:|---:|---:|
| atr_pct_bucket | atr_pctl_q4 | 1 | +12.3pp | $+7,780 |
| entry_month | June | 1 | +12.3pp | $+12,781 |
| ma_align | ma_mixed | 1 | +3.9pp | $+5,616 |
| ma_stack | ma_mixed | 1 | +3.9pp | $+5,616 |
| or_width_bucket | or_wide | 1 | +10.6pp | $+24,249 |
| prior_year_ret_bucket | prior_yr_strong | 1 | +9.5pp | $+5,522 |
| rsi_align | rsi_neutral | 1 | +8.7pp | $+5,786 |
| rsi_bucket | rsi_45_55 | 1 | +8.7pp | $+5,786 |
| week_of_month | 2 | 1 | +16.0pp | $+13,072 |

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

## Caveats

- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.
- Yearly ORB sample is sparse (~1–4 campaigns/year); prefer signals that repeat across books.
- Follow with null/OOS / broker-like filter tests before any size-up or sit-out.

