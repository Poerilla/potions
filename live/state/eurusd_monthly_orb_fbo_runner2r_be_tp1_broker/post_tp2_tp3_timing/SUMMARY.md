# Post-TP3 & early-TP2 timing — FBO 1/1/3

Universe: `eurusd_monthly_orb_fbo_r2r_be1_1_1_3` (promoted runner@2R, BE@TP25).

## 1) After TP3 (2R) is hit

TP3 fills: **27**. Median days left in month: **7**.

| Bucket | N | Hold d+1 | Hold d+3 | Hold d+5 | ME still >2R | Touch 1R | Close thru 1R | Touch BE | Touch 2.5R | Touch 3R | Med MFE/MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_tp3 | 27 | 45.8% | 45.5% | 63.2% | 40.7% | 37.0% | 22.2% | 11.1% | 55.6% | 33.3% | 0.601/0.843 R |
| tp3_with_>=3d_left | 22 | 45.5% | 45.5% | 63.2% | 45.5% | 40.9% | 27.3% | 13.6% | 68.2% | 40.9% | 0.944/0.899 R |
| tp3_with_<3d_left | 5 | 50.0% | None% | None% | 20.0% | 20.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.054/0.618 R |

With **≥3 days left** after TP3 (n=22): hold d+3 **45.5%**, month-end still above 2R **45.5%**, touch back to 1R **40.9%**, touch BE **13.6%**, extend to 3R **40.9%**. Mean month-end edge vs 2R: **-0.149 R**.

## 2) TP2 hit before halfway through the month

Of **60** TP2 hits: **24** (40.0%) before half-month, **36** (60.0%) at/after half.

| Timing | N | Then hit 2R | Median days left | Outcomes |
|---|---:|---:|---:|---|
| tp2_before_half | 24 | 66.7% | 16.0 | hit_2R:16, stop_close:7, month_end:1 |
| tp2_at_or_after_half | 36 | 30.6% | 7.0 | month_end:18, hit_2R:11, stop_close:5, other:2 |

Early TP2 (before half): median post-TP2 MFE/MAE **1.446/0.883 R**, mean month-end edge vs 1R **-0.276 R**.

CSV: `post_tp3_campaigns.csv`, `early_tp2_campaigns.csv`
