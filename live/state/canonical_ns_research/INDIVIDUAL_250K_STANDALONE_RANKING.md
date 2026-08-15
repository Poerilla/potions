# INDIVIDUAL_250K_STANDALONE_RANKING

Policy:

```text
capital=$250,000
stress_budget=$25,000  (10%)
max_MTM_DD=$37,500      (15%)
max_margin=$125,000      (50%)
score=annualized_net_on_250k
tie_breaker=candidate_NS
sizing=continuous fill of stress_budget for score; discrete_copies for lot feasibility
eligibility=canonical rankable + USD-normalized + finite + years_observed>=1
```

Historical cumulative equivalents scaled to the common stress budget, then
divided by years observed. **Not** live projections. 3×/4× sensitivity rows
are excluded here — see `INDIVIDUAL_250K_LEVERAGE_LADDER`.

Selection-aware status is retained: a top N/S expression can be the strongest
research finding without yet being a funded allocation.

Rows ranked: 76 (inside_limits first; min 1y span).

| market | book_id | condition_set | multiplier | selection_status | start_date | end_date | years_observed | size_scale | sizing_mode | scaled_cumulative_net | scaled_net_per_year | annualized_return_on_250k | candidate_NS | worst_calendar_year | worst_calendar_year_net | worst_rolling_12m_net | mtm_dd_pct_of_250k | reachable_stress_pct_of_250k | margin_use_pct_of_250k | inside_limits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00 | BORDERLINE PAPER | 2021-03-04 | 2026-03-05 | 5.00 | 0.47 | fractional_downsize | +906,532 | +181,219 | 72.5% | 36.26 | 2022 | +19,365 | +115,416 | 10.0% | 10.0% | 4.2% | YES |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25 | BORDERLINE PAPER | 2021-03-04 | 2026-03-05 | 5.00 | 0.49 | fractional_downsize | +718,867 | +143,704 | 57.5% | 28.75 | 2022 | +12,710 | +91,523 | 10.0% | 10.0% | 4.3% | YES |
| NQ | nq_prior_opposed_rl | ST-event age=st_age_30_90m | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-05 | 5.00 | 0.47 | fractional_downsize | +688,687 | +137,671 | 55.1% | 27.55 | 2022 | +12,710 | +87,681 | 10.0% | 10.0% | 4.2% | YES |
| NQ | nq_prior_opposed_rl | NQ-ES dispersion=disp_mid | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-05 | 5.00 | 0.43 | fractional_downsize | +617,104 | +123,362 | 49.3% | 24.68 | 2022 | +12,710 | +78,567 | 10.0% | 10.0% | 3.7% | YES |
| MNQ | MNQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2021-03-17 | 2026-02-24 | 4.94 | 20.91 | discrete_book_copies | +484,565 | +98,040 | 39.2% | 19.38 | 2026 | +20,378 | +48,674 | 10.0% | 10.0% | 18.4% | YES |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00 | NOT VALIDATED | 2021-03-04 | 2026-03-03 | 5.00 | 0.82 | fractional_downsize | +413,767 | +82,803 | 33.1% | 16.55 | 2026 | +27,402 | +6,420 | 10.0% | 10.0% | 4.6% | YES |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-03 | 5.00 | 0.88 | fractional_downsize | +342,552 | +68,552 | 27.4% | 13.70 | 2026 | +23,697 | +5,315 | 10.0% | 10.0% | 4.9% | YES |
| ES | es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-03 | 5.00 | 0.87 | fractional_downsize | +328,448 | +65,729 | 26.3% | 13.14 | 2026 | +23,697 | +5,096 | 10.0% | 10.0% | 4.9% | YES |
| ES | es_prior_opposed_legacy | Week of month=1 | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-03 | 5.00 | 0.81 | fractional_downsize | +317,098 | +63,458 | 25.4% | 12.68 | 2026 | +23,697 | +4,920 | 10.0% | 10.0% | 4.6% | YES |
| US30 | US30/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2016-11-21 | 2025-07-09 | 8.63 | 27.56 | discrete_book_copies | +524,308 | +60,763 | 24.3% | 20.97 | 2016 | +11,859 | +16,436 | 10.0% | 10.0% | 5.5% | YES |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 2.00 | NOT VALIDATED | 2021-03-04 | 2026-04-02 | 5.08 | 0.71 | fractional_downsize | +288,865 | +56,874 | 22.7% | 11.55 | 2023 | +24,345 | +8,241 | 10.0% | 10.0% | 2.8% | YES |
| US30 | US30/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2016-11-21 | 2025-07-11 | 8.63 | 8.72 | discrete_book_copies | +489,242 | +56,664 | 22.7% | 19.57 | 2016 | +3,813 | +7,163 | 10.0% | 10.0% | 5.2% | YES |
| NAS100 | NAS100/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2016-12-07 | 2025-09-30 | 8.81 | 32.13 | discrete_book_copies | +488,917 | +55,480 | 22.2% | 19.56 | 2016 | -3,074 | -4,676 | 10.0% | 10.0% | 6.4% | YES |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | 2.00 | LADDER (prefer null-suite) | 2021-03-04 | 2026-04-02 | 5.08 | 0.68 | fractional_downsize | +274,417 | +54,030 | 21.6% | 10.98 | 2023 | +7,211 | +7,829 | 10.0% | 10.0% | 2.7% | YES |
| MNQ | MNQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2021-03-17 | 2026-02-24 | 4.94 | 5.05 | discrete_book_copies | +251,847 | +50,955 | 20.4% | 10.07 | 2026 | +5,875 | +13,789 | 10.0% | 10.0% | 13.3% | YES |
| YM | ym_prior_opposed_rl | Month=12 | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-04-02 | 5.08 | 0.84 | fractional_downsize | +257,991 | +50,796 | 20.3% | 10.32 | 2023 | +9,705 | +7,360 | 10.0% | 10.0% | 3.3% | YES |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-04-02 | 5.08 | 0.80 | fractional_downsize | +256,362 | +50,475 | 20.2% | 10.25 | 2023 | +9,705 | +7,314 | 10.0% | 10.0% | 3.2% | YES |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | 1.25 | RISK-BUDGET PROFILE | 2021-03-04 | 2026-04-02 | 5.08 | 0.81 | fractional_downsize | +256,054 | +50,414 | 20.2% | 10.24 | 2023 | +4,942 | +7,305 | 10.0% | 10.0% | 3.2% | YES |
| NQ | nq_v2b_s113 | Opening 15m range vs ATR=or_norm | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-06 | 5.01 | 0.24 | fractional_downsize | +244,243 | +48,796 | 19.5% | 9.77 | 2022 | +11,342 | +11,871 | 10.0% | 10.0% | 2.1% | YES |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 2.00 | LADDER (prefer null-suite) | 2010-09-14 | 2026-04-29 | 15.62 | 1.73 | discrete_book_copies | +714,256 | +45,719 | 18.3% | 28.57 | 2011 | -21,308 | -16,638 | 10.0% | 10.0% | 15.2% | YES |
| NQ | nq_v2b_s113 | Overnight range third=on_lower | 1.25 | NOT VALIDATED | 2021-03-04 | 2026-03-06 | 5.01 | 0.23 | fractional_downsize | +224,679 | +44,887 | 18.0% | 8.99 | 2022 | +11,342 | +10,920 | 10.0% | 10.0% | 2.0% | YES |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 1.25 | RISK-BUDGET PROFILE | 2021-03-04 | 2026-03-06 | 5.01 | 0.22 | fractional_downsize | +218,707 | +43,694 | 17.5% | 8.75 | 2022 | +11,342 | +10,629 | 10.0% | 10.0% | 1.9% | YES |
| NQ | nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | 2.00 | LADDER (prefer null-suite) | 2021-03-04 | 2026-03-06 | 5.01 | 0.15 | fractional_downsize | +204,556 | +40,867 | 16.3% | 8.18 | 2022 | +8,834 | +9,942 | 10.0% | 10.0% | 1.3% | YES |
| NQ | nq_st_pmc_3r | Overnight compression=on_comp | 1.25 | NOT VALIDATED | 2010-09-14 | 2026-04-29 | 15.62 | 1.61 | discrete_book_copies | +618,626 | +39,598 | 15.8% | 24.75 | 2011 | -17,141 | -14,410 | 10.0% | 10.0% | 14.2% | YES |
| NQ | nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | 1.25 | NOT VALIDATED | 2010-09-14 | 2026-04-29 | 15.62 | 1.51 | discrete_book_copies | +593,067 | +37,962 | 15.2% | 23.72 | 2011 | -17,141 | -13,815 | 10.0% | 10.0% | 13.3% | YES |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 1.25 | RISK-BUDGET PROFILE | 2010-09-14 | 2026-04-29 | 15.62 | 1.58 | discrete_book_copies | +579,003 | +37,061 | 14.8% | 23.16 | 2011 | -17,141 | -13,487 | 10.0% | 10.0% | 13.9% | YES |
| YM | ym_st_pmc_3r | Day of week=Thursday | 2.00 | LADDER (prefer null-suite) | 2010-07-02 | 2026-05-05 | 15.84 | 3.89 | discrete_book_copies | +558,961 | +35,284 | 14.1% | 22.36 | 2010 | +3,863 | -2,571 | 10.0% | 10.0% | 15.4% | YES |
| NQ | NQ/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2010-09-14 | 2026-04-29 | 15.62 | 1.47 | discrete_book_copies | +512,836 | +32,826 | 13.1% | 20.51 | 2011 | -13,320 | -11,858 | 10.0% | 10.0% | 12.9% | YES |
| NAS100 | NAS100/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2016-12-07 | 2025-10-01 | 8.81 | 8.17 | discrete_book_copies | +278,360 | +31,581 | 12.6% | 11.13 | 2016 | -2,377 | +5,784 | 10.0% | 10.0% | 4.9% | YES |
| YM | ym_st_pmc_3r | Day of week=Thursday | 1.25 | RISK-BUDGET PROFILE | 2010-07-02 | 2026-05-05 | 15.84 | 4.15 | discrete_book_copies | +480,076 | +30,305 | 12.1% | 19.20 | 2010 | +344 | -2,208 | 10.0% | 10.0% | 16.4% | YES |
| YM | ym_st_pmc_3r | Overnight compression=on_comp | 1.25 | NOT VALIDATED | 2010-07-02 | 2026-05-05 | 15.84 | 3.90 | discrete_book_copies | +454,413 | +28,685 | 11.5% | 18.18 | 2010 | +344 | -2,090 | 10.0% | 10.0% | 15.4% | YES |
| YM | ym_st_pmc_3r | Prior RTH range percentile=prior_range_norm | 1.25 | NOT VALIDATED | 2010-07-02 | 2026-05-05 | 15.84 | 3.87 | discrete_book_copies | +452,131 | +28,541 | 11.4% | 18.09 | 2010 | +344 | -2,079 | 10.0% | 10.0% | 15.3% | YES |
| YM | YM/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2010-07-02 | 2026-05-05 | 15.84 | 4.15 | discrete_book_copies | +441,547 | +27,873 | 11.1% | 17.66 | 2010 | -742 | -1,727 | 10.0% | 10.0% | 16.4% | YES |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 2.00 | RISK-BUDGET PROFILE | 2015-02-02 | 2026-02-19 | 11.05 | 1.17 | discrete_book_copies | +275,505 | +24,939 | 10.0% | 11.02 | 2026 | -12,531 | +9,009 | 10.0% | 10.0% | 0.9% | YES |
| NQ | nq_or_complement_skipflat | Day of week=Thursday | 1.25 | NOT VALIDATED | 2021-03-05 | 2026-03-04 | 5.00 | 0.18 | fractional_downsize | +120,397 | +24,094 | 9.6% | 4.82 | 2022 | +4,397 | +1,524 | 10.0% | 10.0% | 1.6% | YES |
| NQ | nq_or_complement_skipflat | Opening 15m range vs ATR=or_norm | 1.25 | NOT VALIDATED | 2021-03-05 | 2026-03-04 | 5.00 | 0.17 | fractional_downsize | +117,929 | +23,600 | 9.4% | 4.72 | 2022 | +4,307 | +1,492 | 10.0% | 10.0% | 1.5% | YES |
| YM | YM/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2010-07-02 | 2026-05-05 | 15.84 | 1.17 | discrete_book_copies | +365,601 | +23,079 | 9.2% | 14.62 | 2012 | -10,280 | -13,297 | 10.0% | 10.0% | 13.9% | YES |
| NQ | nq_or_complement_skipflat | Opening 15m volume percentile=vol_low | 1.25 | NOT VALIDATED | 2021-03-05 | 2026-03-04 | 5.00 | 0.18 | fractional_downsize | +113,143 | +22,642 | 9.1% | 4.53 | 2022 | +4,133 | +1,432 | 10.0% | 10.0% | 1.6% | YES |
| NQ | NQ/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2010-09-14 | 2026-05-01 | 15.63 | 0.43 | fractional_downsize | +331,388 | +21,205 | 8.5% | 13.26 | 2016 | +1,211 | +7,546 | 10.0% | 10.0% | 11.3% | YES |
| USDJPY | usdjpy_asia_range | Entry hour (NY)=4 | 1.25 | NOT VALIDATED | 2015-02-02 | 2026-02-19 | 11.05 | 1.17 | discrete_book_copies | +234,151 | +21,195 | 8.5% | 9.37 | 2026 | -10,650 | +7,657 | 10.0% | 10.0% | 0.9% | YES |
| USDJPY | usdjpy_asia_range | 5m MA vs trade=ma_opposed | 1.25 | NOT VALIDATED | 2015-02-02 | 2026-02-19 | 11.05 | 1.19 | discrete_book_copies | +232,432 | +21,040 | 8.4% | 9.30 | 2026 | -10,572 | +7,601 | 10.0% | 10.0% | 0.9% | YES |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 1.25 | RISK-BUDGET PROFILE | 2015-02-02 | 2026-02-19 | 11.05 | 1.20 | discrete_book_copies | +231,401 | +20,946 | 8.4% | 9.26 | 2026 | -10,525 | +7,567 | 10.0% | 10.0% | 1.0% | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 2.00 | NOT VALIDATED | 2003-05-13 | 2026-03-27 | 22.87 | 1.22 | discrete_book_copies | +417,579 | +18,256 | 7.3% | 16.70 | 2003 | -5,528 | -12,353 | 10.0% | 10.0% | 1.0% | YES |
| MYM | MYM/sl50_tp150_3r_1mfill | sl50_tp150_3r_1mfill | 1.00 | BASELINE / FILTER RESEARCH | 2019-06-03 | 2026-03-02 | 6.75 | 18.31 | discrete_book_copies | +119,294 | +17,683 | 7.1% | 4.77 | 2026 | +2,021 | +7,010 | 10.0% | 10.0% | 7.3% | YES |
| USDJPY | usdjpy_monday_or | Week of month=2 | 1.25 | RISK-BUDGET PROFILE | 2003-05-13 | 2026-03-27 | 22.87 | 1.23 | discrete_book_copies | +398,164 | +17,407 | 7.0% | 15.93 | 2003 | -5,271 | -11,778 | 10.0% | 10.0% | 1.0% | YES |
| USDJPY | usdjpy_monday_or | Prior-week range half=week_opposed | 1.25 | RISK-BUDGET PROFILE | 2003-05-13 | 2026-03-27 | 22.87 | 1.07 | discrete_book_copies | +394,738 | +17,258 | 6.9% | 15.79 | 2003 | -5,226 | -11,677 | 10.0% | 10.0% | 0.9% | YES |
| MYM | MYM/sl50_tp150_runners_2r_10r | sl50_tp150_runners_2r_10r | 1.00 | BASELINE / FILTER RESEARCH | 2019-06-03 | 2026-03-02 | 6.75 | 5.60 | discrete_book_copies | +115,266 | +17,086 | 6.8% | 4.61 | 2026 | +170 | +1,817 | 10.0% | 10.0% | 6.6% | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 1.25 | NOT VALIDATED | 2003-05-13 | 2026-03-27 | 22.87 | 1.26 | discrete_book_copies | +383,942 | +16,786 | 6.7% | 15.36 | 2003 | -5,083 | -11,358 | 10.0% | 10.0% | 1.0% | YES |
| USDJPY | S_3_1_3_flt | skip_months+roll50_wr40_pf1 | 1.00 | RISK THROTTLE / PROFILE | 2015-02-02 | 2026-02-19 | 11.05 | 1.02 | discrete_book_copies | +180,839 | +16,370 | 6.5% | 7.23 | 2026 | -8,245 | +5,886 | 10.0% | 10.0% | 5.7% | YES |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=4 | 1.25 | RISK-BUDGET PROFILE | 2003-05-13 | 2026-03-27 | 22.87 | 1.23 | discrete_book_copies | +373,645 | +16,335 | 6.5% | 14.95 | 2003 | -4,946 | -11,053 | 10.0% | 10.0% | 1.0% | YES |
