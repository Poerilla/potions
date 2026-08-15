# INDIVIDUAL_250K_LEVERAGE_LADDER

Sensitivity / size ladder including 3×/4×. **Not** a deployable $250k board.
Metrics still normalized to the same $25k stress budget for comparison.

Rows: 90

| market | book_id | condition_set | multiplier | selection_status | candidate_NS | delta_NS | size_scale | scaled_cumulative_net | scaled_net_per_year | annualized_return_on_250k | mtm_dd_pct_of_250k | reachable_stress_pct_of_250k | margin_use_pct_of_250k | inside_limits | years_observed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EURUSD | EURUSD/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 3.01 | 0.00 | 1.17 | +75,178 | +3,294 | 1.3% | 10.0% | 10.0% | 0.9% | YES | 22.82 |
| EURUSD | EURUSD/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 1.80 | — | 0.37 | +45,001 | +1,972 | 0.8% | 10.0% | 10.0% | 0.9% | YES | 22.82 |
| GBPUSD | GBPUSD/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 8.12 | 0.00 | 1.88 | +202,967 | +8,910 | 3.6% | 10.0% | 10.0% | 1.5% | YES | 22.78 |
| GBPUSD | GBPUSD/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2.47 | — | 0.61 | +61,758 | +2,711 | 1.1% | 10.0% | 10.0% | 1.5% | YES | 22.78 |
| MNQ | MNQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 19.38 | 0.00 | 20.91 | +484,565 | +98,040 | 39.2% | 10.0% | 10.0% | 18.4% | YES | 4.94 |
| MNQ | MNQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 10.07 | — | 5.05 | +251,847 | +50,955 | 20.4% | 10.0% | 10.0% | 13.3% | YES | 4.94 |
| MNQ | MNQ_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 21.51 | 3.07 | 3.52 | +537,698 | — | — | 10.0% | 10.0% | 3.1% | NO | — |
| MYM | MYM/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 4.77 | 0.00 | 18.31 | +119,294 | +17,683 | 7.1% | 10.0% | 10.0% | 7.3% | YES | 6.75 |
| MYM | MYM/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 4.61 | — | 5.60 | +115,266 | +17,086 | 6.8% | 10.0% | 10.0% | 6.6% | YES | 6.75 |
| NAS100 | NAS100/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 19.56 | 0.00 | 32.13 | +488,917 | +55,480 | 22.2% | 10.0% | 10.0% | 6.4% | YES | 8.81 |
| NAS100 | NAS100/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 11.13 | — | 8.17 | +278,360 | +31,581 | 12.6% | 10.0% | 10.0% | 4.9% | YES | 8.81 |
| NAS100 | NAS100_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 0.22 | 0.10 | 3.14 | +5,455 | — | — | 10.0% | 10.0% | 0.6% | NO | — |
| NQ | NQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 20.51 | 0.00 | 1.47 | +512,836 | +32,826 | 13.1% | 10.0% | 10.0% | 12.9% | YES | 15.62 |
| NQ | NQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 13.26 | — | 0.43 | +331,388 | +21,205 | 8.5% | 10.0% | 10.0% | 11.3% | YES | 15.63 |
| NQ | NQ_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 22.54 | 3.14 | 0.36 | +563,483 | — | — | 10.0% | 10.0% | 3.1% | NO | — |
| USDJPY | S_0_5_0_flt | skip_months+roll50_wr40_pf1 | 1.00 | RISK THROTTLE / PROFILE | 6.67 | 4.52 | 1.47 | +166,669 | +15,087 | 6.0% | 10.0% | 10.0% | 5.9% | YES | 11.05 |
| USDJPY | S_3_1_3_flt | skip_months+roll50_wr40_pf1 | 1.00 | RISK THROTTLE / PROFILE | 7.23 | 5.09 | 1.02 | +180,839 | +16,370 | 6.5% | 10.0% | 10.0% | 5.7% | YES | 11.05 |
| USDJPY | S_3_3_3 | unfiltered | 1.00 | RISK THROTTLE / PROFILE | 2.14 | 0.00 | 0.27 | +53,567 | +4,765 | 1.9% | 10.0% | 10.0% | 2.0% | YES | 11.24 |
| USDJPY | S_3_3_3_flt | skip_months+roll50_wr40_pf1 | 1.00 | RISK THROTTLE / PROFILE | 7.11 | 4.97 | 0.79 | +177,708 | +16,058 | 6.4% | 10.0% | 10.0% | 5.7% | YES | 11.07 |
| US30 | US30/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 20.97 | 0.00 | 27.56 | +524,308 | +60,763 | 24.3% | 10.0% | 10.0% | 5.5% | YES | 8.63 |
| US30 | US30/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 19.57 | — | 8.72 | +489,242 | +56,664 | 22.7% | 10.0% | 10.0% | 5.2% | YES | 8.63 |
| US30 | US30_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 0.69 | 0.10 | 2.31 | +17,192 | — | — | 10.0% | 10.0% | 0.5% | NO | — |
| XAUUSD | XAUUSD/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 0.83 | 0.00 | 0.27 | +20,802 | +936 | 0.4% | 10.0% | 10.0% | 0.5% | YES | 22.23 |
| XAUUSD | XAUUSD/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 1.66 | — | 0.15 | +41,393 | +1,862 | 0.7% | 10.0% | 10.0% | 0.9% | YES | 22.23 |
| YM | YM/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 17.66 | 0.00 | 4.15 | +441,547 | +27,873 | 11.1% | 10.0% | 10.0% | 16.4% | YES | 15.84 |
| YM | YM/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 14.62 | — | 1.17 | +365,601 | +23,079 | 9.2% | 10.0% | 10.0% | 13.9% | YES | 15.84 |
| ES | es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | 1.25 | NOT VALIDATED | 13.14 | 0.66 | 0.87 | +328,448 | +65,729 | 26.3% | 10.0% | 10.0% | 4.9% | YES | 5.00 |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25 | NOT VALIDATED | 13.70 | 1.23 | 0.88 | +342,552 | +68,552 | 27.4% | 10.0% | 10.0% | 4.9% | YES | 5.00 |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00 | NOT VALIDATED | 16.55 | 4.08 | 0.82 | +413,767 | +82,803 | 33.1% | 10.0% | 10.0% | 4.6% | YES | 5.00 |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 3.00 | SENSITIVITY ONLY | 18.63 | 6.15 | 0.70 | +465,683 | +93,193 | 37.3% | 10.0% | 10.0% | 3.9% | YES | 5.00 |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 4.00 | SENSITIVITY ONLY | 20.19 | 7.71 | 0.61 | +504,671 | +100,995 | 40.4% | 10.0% | 10.0% | 3.4% | YES | 5.00 |
| ES | es_prior_opposed_legacy | Week of month=1 | 1.25 | NOT VALIDATED | 12.68 | 0.21 | 0.81 | +317,098 | +63,458 | 25.4% | 10.0% | 10.0% | 4.6% | YES | 5.00 |
| ES | es_st_pmc_ma_bull | Day of week=Tuesday | 1.25 | NOT VALIDATED | 2.55 | 0.30 | 0.57 | +63,851 | +4,117 | 1.6% | 10.0% | 10.0% | 3.2% | YES | 15.51 |
| ES | es_st_pmc_ma_bull | Prior RTH range percentile=prior_range_norm | 1.25 | NOT VALIDATED | 2.41 | 0.16 | 0.54 | +60,194 | +3,882 | 1.6% | 10.0% | 10.0% | 3.1% | YES | 15.51 |
| ES | es_st_pmc_ma_bull | ST-event age=st_age_gt180m | 1.25 | RISK THROTTLE | 2.59 | 0.34 | 0.57 | +64,690 | +4,172 | 1.7% | 10.0% | 10.0% | 3.2% | YES | 15.51 |
| EURUSD | eurusd_monday_or | Hourly RSI vs trade=rsi_against_side | 2.00 | RISK-BUDGET PROFILE | 2.77 | 0.88 | 0.47 | +69,337 | +3,035 | 1.2% | 10.0% | 10.0% | 0.4% | YES | 22.84 |
| EURUSD | eurusd_st_pmc_3r | Day of week=Thursday | 1.25 | SIZE-UP VALIDATED | 3.52 | 0.34 | 1.20 | +88,098 | +3,870 | 1.5% | 10.0% | 10.0% | 1.0% | YES | 22.76 |
| EURUSD | eurusd_st_pmc_3r | Day of week=Thursday | 1.50 | BORDERLINE PAPER | 3.85 | 0.67 | 1.17 | +96,214 | +4,227 | 1.7% | 10.0% | 10.0% | 0.9% | YES | 22.76 |
| EURUSD | eurusd_st_pmc_3r | Day of week=Thursday | 2.00 | RISK-BUDGET PROFILE | 4.45 | 1.27 | 1.12 | +111,323 | +4,891 | 2.0% | 10.0% | 10.0% | 0.9% | YES | 22.76 |
| NQ | nq_or_complement_skipflat | Day of week=Thursday | 1.25 | NOT VALIDATED | 4.82 | 0.40 | 0.18 | +120,397 | +24,094 | 9.6% | 10.0% | 10.0% | 1.6% | YES | 5.00 |
| NQ | nq_or_complement_skipflat | Opening 15m range vs ATR=or_norm | 1.25 | NOT VALIDATED | 4.72 | 0.31 | 0.17 | +117,929 | +23,600 | 9.4% | 10.0% | 10.0% | 1.5% | YES | 5.00 |
| NQ | nq_or_complement_skipflat | Opening 15m volume percentile=vol_low | 1.25 | NOT VALIDATED | 4.53 | 0.11 | 0.18 | +113,143 | +22,642 | 9.1% | 10.0% | 10.0% | 1.6% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | NQ-ES dispersion=disp_mid | 1.25 | NOT VALIDATED | 24.68 | 0.62 | 0.43 | +617,104 | +123,362 | 49.3% | 10.0% | 10.0% | 3.7% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25 | BORDERLINE PAPER | 28.75 | 4.70 | 0.49 | +718,867 | +143,704 | 57.5% | 10.0% | 10.0% | 4.3% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00 | BORDERLINE PAPER | 36.26 | 12.20 | 0.47 | +906,532 | +181,219 | 72.5% | 10.0% | 10.0% | 4.2% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 3.00 | SENSITIVITY ONLY | 34.96 | 10.90 | 0.35 | +873,967 | +174,709 | 69.9% | 10.0% | 10.0% | 3.1% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 4.00 | SENSITIVITY ONLY | 34.19 | 10.14 | 0.28 | +854,874 | +170,893 | 68.4% | 10.0% | 10.0% | 2.4% | YES | 5.00 |
| NQ | nq_prior_opposed_rl | ST-event age=st_age_30_90m | 1.25 | NOT VALIDATED | 27.55 | 3.49 | 0.47 | +688,687 | +137,671 | 55.1% | 10.0% | 10.0% | 4.2% | YES | 5.00 |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 1.25 | RISK-BUDGET PROFILE | 23.16 | 1.69 | 1.58 | +579,003 | +37,061 | 14.8% | 10.0% | 10.0% | 13.9% | YES | 15.62 |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 2.00 | LADDER (prefer null-suite) | 28.57 | 7.10 | 1.73 | +714,256 | +45,719 | 18.3% | 10.0% | 10.0% | 15.2% | YES | 15.62 |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 3.00 | SENSITIVITY ONLY | 29.62 | 8.15 | 1.55 | +740,522 | +47,400 | 19.0% | 10.0% | 10.0% | 13.7% | YES | 15.62 |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 4.00 | SENSITIVITY ONLY | 29.85 | 8.38 | 1.38 | +746,210 | +47,764 | 19.1% | 10.0% | 10.0% | 12.1% | YES | 15.62 |
| NQ | nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | 1.25 | NOT VALIDATED | 23.72 | 2.25 | 1.51 | +593,067 | +37,962 | 15.2% | 10.0% | 10.0% | 13.3% | YES | 15.62 |
| NQ | nq_st_pmc_3r | Overnight compression=on_comp | 1.25 | NOT VALIDATED | 24.75 | 3.27 | 1.61 | +618,626 | +39,598 | 15.8% | 10.0% | 10.0% | 14.2% | YES | 15.62 |
| NQ | nq_v2b_s113 | Opening 15m range vs ATR=or_norm | 1.25 | NOT VALIDATED | 9.77 | 0.87 | 0.24 | +244,243 | +48,796 | 19.5% | 10.0% | 10.0% | 2.1% | YES | 5.01 |
| NQ | nq_v2b_s113 | Overnight range third=on_lower | 1.25 | NOT VALIDATED | 8.99 | 0.09 | 0.23 | +224,679 | +44,887 | 18.0% | 10.0% | 10.0% | 2.0% | YES | 5.01 |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 1.25 | RISK-BUDGET PROFILE | 8.75 | -0.15 | 0.22 | +218,707 | +43,694 | 17.5% | 10.0% | 10.0% | 1.9% | YES | 5.01 |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 2.00 | LADDER (prefer null-suite) | 8.18 | -0.71 | 0.15 | +204,556 | +40,867 | 16.3% | 10.0% | 10.0% | 1.3% | YES | 5.01 |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 3.00 | SENSITIVITY ONLY | 7.80 | -1.09 | 0.10 | +195,036 | +38,965 | 15.6% | 10.0% | 10.0% | 0.9% | YES | 5.01 |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 4.00 | SENSITIVITY ONLY | 7.37 | -1.52 | 0.08 | +184,370 | +36,834 | 14.7% | 10.0% | 10.0% | 0.7% | YES | 5.01 |
| US30 | us30_monday_or | Day of week=Friday | 1.25 | NOT VALIDATED | 2.11 | 0.15 | 1.59 | +52,670 | +6,081 | 2.4% | 10.0% | 10.0% | 0.3% | YES | 8.66 |
| US30 | us30_monday_or | Entry hour (NY)=11 | 1.25 | SIZE-UP VALIDATED | 2.16 | 0.20 | 1.53 | +54,116 | +6,248 | 2.5% | 10.0% | 10.0% | 0.3% | YES | 8.66 |
| US30 | us30_monday_or | Entry hour (NY)=11 | 1.50 | BORDERLINE PAPER | 2.36 | 0.40 | 1.49 | +58,980 | +6,809 | 2.7% | 10.0% | 10.0% | 0.3% | YES | 8.66 |
| US30 | us30_monday_or | Entry hour (NY)=11 | 2.00 | RISK-BUDGET PROFILE | 2.72 | 0.76 | 1.42 | +68,047 | +7,856 | 3.1% | 10.0% | 10.0% | 0.3% | YES | 8.66 |
| USDJPY | usdjpy_asia_range | 5m MA vs trade=ma_opposed | 1.25 | NOT VALIDATED | 9.30 | 0.65 | 1.19 | +232,432 | +21,040 | 8.4% | 10.0% | 10.0% | 0.9% | YES | 11.05 |
| USDJPY | usdjpy_asia_range | Entry hour (NY)=4 | 1.25 | NOT VALIDATED | 9.37 | 0.72 | 1.17 | +234,151 | +21,195 | 8.5% | 10.0% | 10.0% | 0.9% | YES | 11.05 |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 1.25 | RISK-BUDGET PROFILE | 9.26 | 0.61 | 1.20 | +231,401 | +20,946 | 8.4% | 10.0% | 10.0% | 1.0% | YES | 11.05 |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 2.00 | RISK-BUDGET PROFILE | 11.02 | 2.37 | 1.17 | +275,505 | +24,939 | 10.0% | 10.0% | 10.0% | 0.9% | YES | 11.05 |
| USDJPY | usdjpy_monday_or | Day of week=Thursday | 1.25 | NOT VALIDATED | 14.31 | -0.16 | 1.17 | +357,845 | +15,645 | 6.3% | 10.0% | 10.0% | 0.9% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=4 | 1.25 | RISK-BUDGET PROFILE | 14.95 | 0.47 | 1.23 | +373,645 | +16,335 | 6.5% | 10.0% | 10.0% | 1.0% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 1.25 | NOT VALIDATED | 15.36 | 0.88 | 1.26 | +383,942 | +16,786 | 6.7% | 10.0% | 10.0% | 1.0% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 2.00 | NOT VALIDATED | 16.70 | 2.23 | 1.22 | +417,579 | +18,256 | 7.3% | 10.0% | 10.0% | 1.0% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 1.25 | NOT VALIDATED | 14.26 | -0.21 | 1.16 | +356,494 | +15,586 | 6.2% | 10.0% | 10.0% | 0.9% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Prior-week range half=week_opposed | 1.25 | RISK-BUDGET PROFILE | 15.79 | 1.32 | 1.07 | +394,738 | +17,258 | 6.9% | 10.0% | 10.0% | 0.9% | YES | 22.87 |
| USDJPY | usdjpy_monday_or | Week of month=2 | 1.25 | RISK-BUDGET PROFILE | 15.93 | 1.45 | 1.23 | +398,164 | +17,407 | 7.0% | 10.0% | 10.0% | 1.0% | YES | 22.87 |
| YM | ym_prior_opposed_rl | Month=12 | 1.25 | NOT VALIDATED | 10.32 | 0.58 | 0.84 | +257,991 | +50,796 | 20.3% | 10.0% | 10.0% | 3.3% | YES | 5.08 |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 1.25 | NOT VALIDATED | 10.25 | 0.51 | 0.80 | +256,362 | +50,475 | 20.2% | 10.0% | 10.0% | 3.2% | YES | 5.08 |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 2.00 | NOT VALIDATED | 11.55 | 1.81 | 0.71 | +288,865 | +56,874 | 22.7% | 10.0% | 10.0% | 2.8% | YES | 5.08 |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 3.00 | SENSITIVITY ONLY | 12.88 | 3.14 | 0.61 | +321,900 | +63,378 | 25.4% | 10.0% | 10.0% | 2.4% | YES | 5.08 |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 4.00 | SENSITIVITY ONLY | 13.88 | 4.14 | 0.54 | +347,032 | +68,327 | 27.3% | 10.0% | 10.0% | 2.1% | YES | 5.08 |
