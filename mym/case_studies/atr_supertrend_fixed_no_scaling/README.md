# MYM ATR Supertrend Fixed No-Scaling Summary

> **Legacy summary.** A Pine parity review on 2026-05-08 found that the old weekly-primary rows were mislabeled: the Python weekly ATR mapper inherited existing daily ATR columns in some paths. The weekly rows below are preserved as research artifacts, not live-test expectations. Corrected runs are in `mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/` and `mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/`.

Point value used here is MYM = $0.50/point. These are fixed 10-max variants, before the yearly equity-scaling overlay.

| Variant | Stacks | Units | Net | Closed DD | MTM DD | Worst MAE | Avg MAE | Win Rate | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily primary, 3-initial | 63 | 261 | $40,908 | $-4,642 | $-9,223 | $-3,244 | $-559 | 30.2% | 3.00 |
| Daily primary, ladder 1/1/2/2/2 | 63 | 174 | $24,173 | $-5,510 | $-10,600 | $-3,786 | $-374 | 23.8% | 2.75 |
| Weekly primary, 3-initial | 45 | 220 | $81,587 | $-1,922 | $-7,292 | $-1,348 | $-345 | 57.8% | 15.04 |
| Weekly primary, ladder 1/1/2/2/2 | 45 | 173 | $43,638 | $-2,012 | $-8,230 | $-1,565 | $-343 | 44.4% | 8.34 |
