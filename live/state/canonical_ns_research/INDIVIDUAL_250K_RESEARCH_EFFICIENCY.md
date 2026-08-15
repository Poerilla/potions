# INDIVIDUAL_250K_RESEARCH_EFFICIENCY

Policy:

```text
score=candidate_NS
tie_breaker=delta_NS
```

Preserves research ranking under N/S (not $250k annualization).
Same deployable universe (no 3×/4× sensitivity-only rows).

Rows: 76

| market | book_id | condition_set | multiplier | selection_status | candidate_NS | delta_NS | native_net | native_stress | years_observed | scaled_net_per_year | inside_limits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00 | BORDERLINE PAPER | 36.26 | 12.20 | +1,912,872 | +52,752 | 5.00 | +181,219 | YES |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25 | BORDERLINE PAPER | 28.75 | 4.70 | +1,476,408 | +51,345 | 5.00 | +143,704 | YES |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 2.00 | LADDER (prefer null-suite) | 28.57 | 7.10 | +413,266 | +14,465 | 15.62 | +45,719 | YES |
| NQ | nq_prior_opposed_rl | ST-event age=st_age_30_90m | 1.25 | NOT VALIDATED | 27.55 | 3.49 | +1,456,574 | +52,875 | 5.00 | +137,671 | YES |
| NQ | nq_st_pmc_3r | Overnight compression=on_comp | 1.25 | NOT VALIDATED | 24.75 | 3.27 | +384,501 | +15,538 | 15.62 | +39,598 | YES |
| NQ | nq_prior_opposed_rl | NQ-ES dispersion=disp_mid | 1.25 | NOT VALIDATED | 24.68 | 0.62 | +1,452,000 | +58,823 | 5.00 | +123,362 | YES |
| NQ | nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | 1.25 | NOT VALIDATED | 23.72 | 2.25 | +392,363 | +16,540 | 15.62 | +37,962 | YES |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 1.25 | RISK-BUDGET PROFILE | 23.16 | 1.69 | +365,454 | +15,779 | 15.62 | +37,061 | YES |
| NQ | NQ_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 22.54 | 3.14 | +1,576,969 | +69,965 | — | — | NO |
| YM | ym_st_pmc_3r | Day of week=Thursday | 2.00 | LADDER (prefer null-suite) | 22.36 | 4.30 | +143,725 | +6,428 | 15.84 | +35,284 | YES |
| MNQ | MNQ_10r_addon | prior_opposed+10R | 1.00 | INSUFFICIENT_SPAN (ADDON (not finite-core)) | 21.51 | 3.07 | +152,588 | +7,094 | — | — | NO |
| US30 | US30/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 20.97 | 0.00 | +19,028 | +907 | 8.63 | +60,763 | YES |
| NQ | NQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 20.51 | 0.00 | +349,517 | +17,038 | 15.62 | +32,826 | YES |
| US30 | US30/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 19.57 | — | +56,111 | +2,867 | 8.63 | +56,664 | YES |
| NAS100 | NAS100/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 19.56 | 0.00 | +15,219 | +778 | 8.81 | +55,480 | YES |
| MNQ | MNQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 19.38 | 0.00 | +23,171 | +1,195 | 4.94 | +98,040 | YES |
| YM | ym_st_pmc_3r | Day of week=Thursday | 1.25 | RISK-BUDGET PROFILE | 19.20 | 1.15 | +115,750 | +6,028 | 15.84 | +30,305 | YES |
| YM | ym_st_pmc_3r | Overnight compression=on_comp | 1.25 | NOT VALIDATED | 18.18 | 0.12 | +116,556 | +6,412 | 15.84 | +28,685 | YES |
| YM | ym_st_pmc_3r | Prior RTH range percentile=prior_range_norm | 1.25 | NOT VALIDATED | 18.09 | 0.03 | +116,821 | +6,459 | 15.84 | +28,541 | YES |
| YM | YM/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 17.66 | 0.00 | +106,425 | +6,026 | 15.84 | +27,873 | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 2.00 | NOT VALIDATED | 16.70 | 2.23 | +341,469 | +20,443 | 22.87 | +18,256 | YES |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00 | NOT VALIDATED | 16.55 | 4.08 | +506,865 | +30,625 | 5.00 | +82,803 | YES |
| USDJPY | usdjpy_monday_or | Week of month=2 | 1.25 | RISK-BUDGET PROFILE | 15.93 | 1.45 | +323,775 | +20,329 | 22.87 | +17,407 | YES |
| USDJPY | usdjpy_monday_or | Prior-week range half=week_opposed | 1.25 | RISK-BUDGET PROFILE | 15.79 | 1.32 | +367,775 | +23,292 | 22.87 | +17,258 | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 1.25 | NOT VALIDATED | 15.36 | 0.88 | +305,842 | +19,915 | 22.87 | +16,786 | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=4 | 1.25 | RISK-BUDGET PROFILE | 14.95 | 0.47 | +303,575 | +20,312 | 22.87 | +16,335 | YES |
| YM | YM/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 14.62 | — | +313,302 | +21,424 | 15.84 | +23,079 | YES |
| USDJPY | usdjpy_monday_or | Day of week=Thursday | 1.25 | NOT VALIDATED | 14.31 | -0.16 | +306,975 | +21,446 | 22.87 | +15,645 | YES |
| USDJPY | usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | 1.25 | NOT VALIDATED | 14.26 | -0.21 | +307,804 | +21,586 | 22.87 | +15,586 | YES |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25 | NOT VALIDATED | 13.70 | 1.23 | +388,232 | +28,334 | 5.00 | +68,552 | YES |
| NQ | NQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 13.26 | — | +775,763 | +58,524 | 15.63 | +21,205 | YES |
| ES | es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | 1.25 | NOT VALIDATED | 13.14 | 0.66 | +377,904 | +28,764 | 5.00 | +65,729 | YES |
| ES | es_prior_opposed_legacy | Week of month=1 | 1.25 | NOT VALIDATED | 12.68 | 0.21 | +389,468 | +30,706 | 5.00 | +63,458 | YES |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 2.00 | NOT VALIDATED | 11.55 | 1.81 | +407,098 | +35,232 | 5.08 | +56,874 | YES |
| NAS100 | NAS100/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 11.13 | — | +34,065 | +3,059 | 8.81 | +31,581 | YES |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 2.00 | RISK-BUDGET PROFILE | 11.02 | 2.37 | +236,082 | +21,423 | 11.05 | +24,939 | YES |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | 2.00 | LADDER (prefer null-suite) | 10.98 | 1.24 | +400,635 | +36,499 | 5.08 | +54,030 | YES |
| YM | ym_prior_opposed_rl | Month=12 | 1.25 | NOT VALIDATED | 10.32 | 0.58 | +306,429 | +29,694 | 5.08 | +50,796 | YES |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 1.25 | NOT VALIDATED | 10.25 | 0.51 | +318,693 | +31,078 | 5.08 | +50,475 | YES |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | 1.25 | RISK-BUDGET PROFILE | 10.24 | 0.50 | +317,078 | +30,958 | 5.08 | +50,414 | YES |
| MNQ | MNQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 10.07 | — | +49,899 | +4,953 | 4.94 | +50,955 | YES |
| NQ | nq_v2b_s113 | Opening 15m range vs ATR=or_norm | 1.25 | NOT VALIDATED | 9.77 | 0.87 | +1,022,566 | +104,667 | 5.01 | +48,796 | YES |
| USDJPY | usdjpy_asia_range | Entry hour (NY)=4 | 1.25 | NOT VALIDATED | 9.37 | 0.72 | +200,485 | +21,406 | 11.05 | +21,195 | YES |
| USDJPY | usdjpy_asia_range | 5m MA vs trade=ma_opposed | 1.25 | NOT VALIDATED | 9.30 | 0.65 | +195,916 | +21,072 | 11.05 | +21,040 | YES |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 1.25 | RISK-BUDGET PROFILE | 9.26 | 0.61 | +192,853 | +20,835 | 11.05 | +20,946 | YES |
| NQ | nq_v2b_s113 | Overnight range third=on_lower | 1.25 | NOT VALIDATED | 8.99 | 0.09 | +983,551 | +109,439 | 5.01 | +44,887 | YES |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 1.25 | RISK-BUDGET PROFILE | 8.75 | -0.15 | +991,302 | +113,314 | 5.01 | +43,694 | YES |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 2.00 | LADDER (prefer null-suite) | 8.18 | -0.71 | +1,363,143 | +166,598 | 5.01 | +40,867 | YES |
| GBPUSD | GBPUSD/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 8.12 | 0.00 | +108,058 | +13,310 | 22.78 | +8,910 | YES |
| USDJPY | S_3_1_3_flt | skip_months+roll50_wr40_pf1 | 1.00 | RISK THROTTLE / PROFILE | 7.23 | 5.09 | +178,142 | +24,627 | 11.05 | +16,370 | YES |
