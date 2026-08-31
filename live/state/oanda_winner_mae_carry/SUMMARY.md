# OANDA winner MAE + percentile carry (p80/85/90/95)

Generated: `2026-08-15T05:42:09Z`

Counterfactual stop = **pXX of winning-trade path MAE**. Sweep **80 / 85 / 90 / 95**.
Daemon stays on avg loss unless a percentile is favorable; recommend best Δnet (tie → tighter).

| demo | inst | p80 | Δ80 | p85 | Δ85 | p90 | Δ90 | p95 | Δ95 | thr | favor |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| us30_hourly_st_pmc_sl50_tp150_3r_oanda | US30 | 35.680 | -4124 | 39.090 | -2969 | 42.761 | -2010 | 46.784 | -1085 | avg_loss | no |
| us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda | US30 | 36.654 | -10184 | 40.332 | -8060 | 42.386 | -6037 | 46.807 | -2266 | avg_loss | no |
| nas100_hourly_st_pmc_sl50_tp150_3r_oanda | NAS100 | 32.431 | -2215 | 36.576 | -1664 | 40.534 | -973 | 45.955 | -624 | avg_loss | no |
| nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda | NAS100 | 30.421 | -3786 | 34.326 | -2066 | 38.899 | -1132 | 40.838 | 3238 | p95_winner_mae | YES |
| eurusd_hourly_st_pmc_sl50_tp150_3r_oanda | EURUSD | 0.003 | 16062 | 0.004 | 13188 | 0.004 | 8571 | 0.005 | 5165 | p80_winner_mae | YES |
| eurusd_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda | EURUSD | 0.004 | -49409 | 0.004 | -38421 | 0.004 | -22422 | 0.005 | -26142 | avg_loss | no |
| usdjpy_asia_range_london_oanda | USDJPY | 0.193 | -14107623 | 0.234 | -12308567 | 0.262 | -6872796 | 0.339 | -2257577 | avg_loss | no |
| us30_london_prior_opposed_oanda | US30 | 39.300 | -11137 | 46.300 | -9465 | 61.300 | -6771 | 70.300 | -2947 | avg_loss | no |
| us30_monday_or_m3_s3_r2_half_oanda | US30 | 104.100 | -24156 | 116.100 | -11326 | 143.100 | -9853 | 181.100 | -2475 | avg_loss | no |
| usdjpy_monday_or_ungated_oanda | USDJPY | 0.256 | -14572820 | 0.301 | -11205330 | 0.353 | -9544160 | 0.499 | -8077010 | avg_loss | no |
| audjpy_yearly_orb_oanda | AUDJPY | 0.261 | -8053140 | 0.350 | -5389575 | 0.484 | -4186525 | 0.721 | -2081900 | avg_loss | no |
| xauusd_yearly_orb_oanda | XAUUSD | 4.258 | -301686 | 5.102 | -240754 | 7.480 | -223952 | 11.640 | -25491 | avg_loss | no |
| xagusd_yearly_orb_oanda | XAGUSD | 0.226 | -45869 | 0.264 | -27695 | 0.277 | -17627 | 0.347 | -9375 | avg_loss | no |
| eurusd_yearly_orb_oanda | EURUSD | 0.003 | -41151 | 0.005 | -36185 | 0.006 | -28922 | 0.009 | -17270 | avg_loss | no |
| us30_yearly_orb_oanda | US30 | 148.000 | -14914 | 153.150 | -7101 | 184.200 | -3776 | 221.400 | -3032 | avg_loss | no |

Favorable books (any pct): **2 / 15**

## Favorable detail

| demo | recommended | Δnet |
|---|---|---:|
| nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda | p95_winner_mae | 3238 |
| eurusd_hourly_st_pmc_sl50_tp150_3r_oanda | p80_winner_mae | 16062 |
