# Futures intraday condition profile

Study: `futures_intraday_hp_sizeup_v1`

Diagnostic + shortlist for 1.25× HP size-up. Not a promotion gate by itself.

## Selected books (top 8 after sleeve/family dedup)

| book | symbol | family | tracker N/S | campaigns | status |
|---|---|---|---:|---:|---|
| es_prior_opposed_legacy | ES | prior_opposed | 10.51 | 245 | strongest-candidate |
| es_st_pmc_ma_bull | ES | st_pmc | 2.13 | 223 | strongest-candidate |

## Baselines

| book | n | net | stress | N/S | WR |
|---|---:|---:|---:|---:|---:|
| es_prior_opposed_legacy | 245 | +348688 | 27950 | 12.48 | 63.7% |
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

## Cross-book notable repeats

| condition=bucket | books | n |
|---|---|---:|
| ST-event age=st_age_gt180m | es_prior_opposed_legacy,es_st_pmc_ma_bull | 2 |
| Week of month=1 | es_prior_opposed_legacy,es_st_pmc_ma_bull | 2 |
| ATR causal rolling percentile=atr_p50_75 | es_st_pmc_ma_bull | 1 |
| ATR causal rolling percentile=atr_p75_100 | es_prior_opposed_legacy | 1 |
| ATR14 quartile=atr_q1 | es_st_pmc_ma_bull | 1 |
| ATR14 quartile=atr_q2 | es_st_pmc_ma_bull | 1 |
| ATR14 quartile=atr_q3 | es_st_pmc_ma_bull | 1 |
| Day of week=Tuesday | es_st_pmc_ma_bull | 1 |
| Entry hour (NY)=10 | es_st_pmc_ma_bull | 1 |
| Monthly OR direction=mor_up | es_st_pmc_ma_bull | 1 |
| NQ-ES dispersion=disp_high | es_st_pmc_ma_bull | 1 |
| Prior RTH range percentile=prior_range_comp | es_st_pmc_ma_bull | 1 |
| Prior RTH range percentile=prior_range_exp | es_prior_opposed_legacy | 1 |
| Prior RTH range percentile=prior_range_norm | es_st_pmc_ma_bull | 1 |
| Week of month=2 | es_prior_opposed_legacy | 1 |

## Carry-over vs futures-native

- Carry: Thu/Fri DOW, RSI against / extremes, ATR regime, prior-week opposition,
  week-of-month, entry hour, MA **opposition** (not generic 5m MA-cross).
- Futures-native: overnight location/compression, prior RTH structure, OR15,
  VWAP, opening volume, ES/NQ/YM agreement, ST-age proxy, roll/holiday flags.
- HTF: yearly ORB up/down/inside, monthly OR up/down/inside, prior-quarter
  inside/breakout type, weekly ATR SuperTrend align/oppose.

Artifacts: `condition_matrix.csv`, `candidate_ledger.csv`, `causal_feature_audit.csv`,
`*_campaigns.csv`, `SELECTED_BOOKS.json`.
