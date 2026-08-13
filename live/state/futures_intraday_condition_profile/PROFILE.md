# Futures intraday condition profile

Study: `futures_intraday_hp_sizeup_v1`

Diagnostic + shortlist for 1.25× HP size-up. Not a promotion gate by itself.

## Selected books (top 8 after sleeve/family dedup)

| book | symbol | family | tracker N/S | campaigns | status |
|---|---|---|---:|---:|---|
| nq_or_complement_skipflat | NQ | session_range | 22.51 | 729 | research-promoted |
| nq_st_pmc_3r | NQ | st_pmc | 20.51 | 679 | research-promoted |
| nq_prior_opposed_rl | NQ | prior_opposed | 19.40 | 432 | research-promoted |
| nq_v2b_s113 | NQ | opening_range | 7.34 | 1386 | research-promoted |
| ym_st_pmc_3r | YM | st_pmc | 17.66 | 985 | research-promoted |
| es_prior_opposed_legacy | ES | prior_opposed | 10.51 | 245 | strongest-candidate |
| ym_prior_opposed_rl | YM | prior_opposed | 8.53 | 436 | research-promoted |
| es_st_pmc_ma_bull | ES | st_pmc | 2.13 | 223 | strongest-candidate |

## Baselines

| book | n | net | stress | N/S | WR |
|---|---:|---:|---:|---:|---:|
| nq_or_complement_skipflat | 729 | +590282 | 133785 | 4.41 | 54.6% |
| nq_st_pmc_3r | 679 | +349517 | 16277 | 21.47 | 38.3% |
| nq_prior_opposed_rl | 432 | +1330920 | 55318 | 24.06 | 66.0% |
| nq_v2b_s113 | 1386 | +867355 | 97510 | 8.90 | 53.8% |
| ym_st_pmc_3r | 985 | +106425 | 5894 | 18.06 | 36.8% |
| es_prior_opposed_legacy | 245 | +348688 | 27950 | 12.48 | 63.7% |
| ym_prior_opposed_rl | 436 | +289225 | 29694 | 9.74 | 61.0% |
| es_st_pmc_ma_bull | 223 | +96230 | 42738 | 2.25 | 29.6% |

## Shortlisted candidates (≤3/book, ≤1/family, cov 5–35%)

| book | condition=bucket | fam | cov | n | avg lift | inc N/S | z_WR |
|---|---|---|---:|---:|---:|---:|---:|
| es_prior_opposed_legacy | ST-event age=st_age_gt180m | st_state | 28% | 68 | +903 | 22.98 | 1.27 |
| es_prior_opposed_legacy | Week of month=1 | calendar | 29% | 72 | +842 | 10.91 | 0.25 |
| es_prior_opposed_legacy | Prior RTH close location=prior_close_mid_third | prior_rth | 25% | 61 | +493 | 10.56 | 0.51 |
| es_st_pmc_ma_bull | Day of week=Tuesday | calendar | 22% | 50 | +859 | 5.13 | 1.18 |
| es_st_pmc_ma_bull | ST-event age=st_age_gt180m | st_state | 28% | 62 | +705 | 3.70 | 1.14 |
| es_st_pmc_ma_bull | Prior RTH range percentile=prior_range_norm | prior_rth | 26% | 57 | +568 | 2.83 | 0.81 |
| nq_or_complement_skipflat | Day of week=Thursday | calendar | 20% | 144 | +961 | 5.16 | 0.36 |
| nq_or_complement_skipflat | Opening 15m range vs ATR=or_norm | opening_structure | 29% | 214 | +1182 | 4.74 | 1.47 |
| nq_or_complement_skipflat | Opening 15m volume percentile=vol_low | participation | 29% | 214 | +117 | 4.63 | 0.50 |
| nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | opening_structure | 30% | 129 | +1430 | 29.31 | 0.96 |
| nq_prior_opposed_rl | ST-event age=st_age_30_90m | st_state | 27% | 118 | +1179 | 20.73 | 0.89 |
| nq_prior_opposed_rl | NQ-ES dispersion=disp_mid | cross_index | 32% | 138 | +429 | 15.99 | 0.62 |
| nq_st_pmc_3r | Overnight compression=on_comp | overnight_compression | 30% | 203 | +175 | 23.01 | 1.05 |
| nq_st_pmc_3r | Entry hour (NY)=11 | calendar | 8% | 56 | +624 | 21.11 | 2.26 |
| nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | momentum_rsi | 32% | 216 | +279 | 20.25 | 1.99 |
| nq_v2b_s113 | Prior RTH close location=prior_close_mid_third | prior_rth | 24% | 339 | +837 | 6.06 | 1.52 |
| nq_v2b_s113 | Opening 15m range vs ATR=or_norm | opening_structure | 30% | 416 | +867 | 6.04 | 1.30 |
| nq_v2b_s113 | Overnight range third=on_lower | overnight_location | 33% | 459 | +387 | 4.51 | 0.89 |
| ym_prior_opposed_rl | Overnight range third=on_middle | overnight_location | 25% | 108 | +428 | 14.17 | 2.32 |
| ym_prior_opposed_rl | Month=12 | calendar | 9% | 40 | +1057 | 10.83 | 1.74 |
| ym_prior_opposed_rl | Prior RTH range percentile=prior_range_norm | prior_rth | 29% | 128 | +207 | 10.28 | 1.42 |
| ym_st_pmc_3r | Day of week=Thursday | calendar | 22% | 215 | +65 | 20.30 | 1.79 |
| ym_st_pmc_3r | Overnight compression=on_comp | overnight_compression | 28% | 279 | +37 | 15.80 | 1.04 |
| ym_st_pmc_3r | Prior RTH range percentile=prior_range_norm | prior_rth | 29% | 282 | +39 | 14.42 | 1.35 |

## Cross-book notable repeats

| condition=bucket | books | n |
|---|---|---:|
| Week of month=2 | es_prior_opposed_legacy,nq_or_complement_skipflat,nq_prior_opposed_rl,nq_v2b_s113,ym_prior_opposed_rl | 5 |
| Day of week=Friday | nq_or_complement_skipflat,nq_prior_opposed_rl,nq_v2b_s113,ym_prior_opposed_rl,ym_st_pmc_3r | 5 |
| Month=4 | nq_or_complement_skipflat,nq_st_pmc_3r,ym_st_pmc_3r | 3 |
| Entry hour (NY)=10 | es_st_pmc_ma_bull,nq_or_complement_skipflat,ym_prior_opposed_rl | 3 |
| ATR causal rolling percentile=atr_p50_75 | es_st_pmc_ma_bull,nq_or_complement_skipflat,nq_v2b_s113 | 3 |
| Month=10 | nq_prior_opposed_rl,nq_v2b_s113,ym_st_pmc_3r | 3 |
| Prior RTH range percentile=prior_range_norm | es_st_pmc_ma_bull,nq_or_complement_skipflat,ym_st_pmc_3r | 3 |
| Opening 15m range vs ATR=or_norm | nq_or_complement_skipflat,nq_prior_opposed_rl,nq_v2b_s113 | 3 |
| ST-event age=st_age_90_180m | nq_or_complement_skipflat,nq_st_pmc_3r,nq_v2b_s113 | 3 |
| Hourly RSI bucket=rsi_55_70 | nq_or_complement_skipflat,nq_st_pmc_3r,nq_v2b_s113 | 3 |
| Day of week=Thursday | nq_or_complement_skipflat,nq_v2b_s113,ym_st_pmc_3r | 3 |
| Day of week=Tuesday | es_st_pmc_ma_bull,nq_v2b_s113 | 2 |
| Hourly RSI vs trade=rsi_against_side | nq_prior_opposed_rl,ym_prior_opposed_rl | 2 |
| Overnight range third=on_lower | nq_or_complement_skipflat,nq_v2b_s113 | 2 |
| Prior RTH close location=prior_close_mid_third | nq_or_complement_skipflat,nq_v2b_s113 | 2 |
| Month=5 | nq_st_pmc_3r,ym_st_pmc_3r | 2 |
| Week of month=1 | es_prior_opposed_legacy,es_st_pmc_ma_bull | 2 |
| Month=2 | nq_st_pmc_3r,nq_v2b_s113 | 2 |
| Month=12 | nq_v2b_s113,ym_prior_opposed_rl | 2 |
| Month=11 | nq_or_complement_skipflat,nq_v2b_s113 | 2 |
| ST-event direction vs trade=st_opposed_proxy | nq_prior_opposed_rl,ym_prior_opposed_rl | 2 |
| Month=1 | nq_or_complement_skipflat,ym_prior_opposed_rl | 2 |
| Prior RTH range percentile=prior_range_exp | es_prior_opposed_legacy,ym_prior_opposed_rl | 2 |
| ATR14 quartile=atr_q3 | es_st_pmc_ma_bull,nq_st_pmc_3r | 2 |
| ATR14 quartile=atr_q4 | nq_st_pmc_3r,ym_prior_opposed_rl | 2 |

## Carry-over vs futures-native

- Carry: Thu/Fri DOW, RSI against / extremes, ATR regime, prior-week opposition,
  week-of-month, entry hour, MA **opposition** (not generic 5m MA-cross).
- Futures-native: overnight location/compression, prior RTH structure, OR15,
  VWAP, opening volume, ES/NQ/YM agreement, ST-age proxy, roll/holiday flags.

Artifacts: `condition_matrix.csv`, `candidate_ledger.csv`, `causal_feature_audit.csv`,
`*_campaigns.csv`, `SELECTED_BOOKS.json`.
