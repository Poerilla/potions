# Post-TP2 (1R) path study — FBO 1/1/3 runner@2R

Universe: **60** campaigns that filled TP2 (1R) on `eurusd_monthly_orb_fbo_r2r_be1_1_1_3`.
After TP2, BE is already on; runner targets 2R. Measured on remaining daily bars in the month.

## Headline

| Metric | Value |
|---|---:|
| TP2 hits | 60 |
| Then fill 2R (tp3) | 41.7% |
| Touch 2R on path (incl. no fill) | 45.0% |
| Touch entry/BE after TP2 | 40.0% |
| Daily close through entry after TP2 | 30.0% |
| Median MFE after TP2 | 0.802 R |
| Median MAE after TP2 | 0.86 R |
| Close still favorable d+1 | 42.4% |
| Close still favorable d+3 | 49.1% |
| Close still favorable d+5 | 57.4% |
| Mean close edge d+1 | -0.025 R |
| Mean close edge d+3 | 0.106 R |
| Mean close edge d+5 | 0.235 R |

## Runner outcome after TP2

| Outcome | N | % |
|---|---:|---:|
| hit_2R | 25 | 41.7% |
| month_end | 19 | 31.7% |
| stop_close_after_tp2 | 12 | 20.0% |
| other | 4 | 6.7% |

## Read

At d+3 after TP2, price roughly a **coin flip** relative to the 1R level (49.1% closes still in favor). Only **41.7%** convert the runner to 2R, while **40.0%** wick/touch back to entry after TP2 (close-through entry 30.0%). Median post-TP2 excursion: MFE 0.802R vs MAE 0.86R.

CSV: `post_tp2_campaigns.csv`
