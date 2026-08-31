# NAS100 NQ-lead prior-opposed HP condition profile (add-on)

Dedicated hub — does **not** rewrite `futures_intraday_condition_profile/` or the ES/YM/NQ LIVE_PLAN.

# Futures intraday condition profile

Study: `futures_intraday_hp_sizeup_v1`

Diagnostic + shortlist for 1.25× HP size-up. Not a promotion gate by itself.

## Selected books (top 8 after sleeve/family dedup)

| book | symbol | family | tracker N/S | campaigns | status |
|---|---|---|---:|---:|---|
| nas100_nq_lead_prior_opposed | NAS100 | prior_opposed | 17.94 | 280 | research-promoted |

## Baselines

| book | n | net | stress | N/S | WR |
|---|---:|---:|---:|---:|---:|
| nas100_nq_lead_prior_opposed | 280 | +21130 | 1178 | 17.94 | 67.9% |

## Shortlisted candidates (≤3/book, ≤1/family, cov 5–35%)

| book | condition=bucket | fam | cov | n | avg lift | inc N/S | z_WR |
|---|---|---|---:|---:|---:|---:|---:|
| nas100_nq_lead_prior_opposed | Hourly RSI vs trade=rsi_against_side | momentum_rsi | 34% | 94 | +56 | 21.24 | 1.95 |
| nas100_nq_lead_prior_opposed | ST-event direction vs trade=st_opposed_proxy | st_state | 34% | 94 | +56 | 21.24 | 1.95 |
| nas100_nq_lead_prior_opposed | Overnight compression=on_comp | overnight_compression | 30% | 83 | +3 | 12.81 | 1.38 |

## Cross-book notable repeats

| condition=bucket | books | n |
|---|---|---:|
| 5m MA vs trade=ma_opposed | nas100_nq_lead_prior_opposed | 1 |
| ATR causal rolling percentile=atr_p25_50 | nas100_nq_lead_prior_opposed | 1 |
| ATR14 quartile=atr_q3 | nas100_nq_lead_prior_opposed | 1 |
| Hourly RSI vs trade=rsi_against_side | nas100_nq_lead_prior_opposed | 1 |
| Opening 15m range vs ATR=or_norm | nas100_nq_lead_prior_opposed | 1 |
| Prior RTH close location=prior_close_mid_third | nas100_nq_lead_prior_opposed | 1 |
| ST-event age=st_age_90_180m | nas100_nq_lead_prior_opposed | 1 |
| ST-event direction vs trade=st_opposed_proxy | nas100_nq_lead_prior_opposed | 1 |
| Week of month=2 | nas100_nq_lead_prior_opposed | 1 |

## Carry-over vs futures-native

- Carry: Thu/Fri DOW, RSI against / extremes, ATR regime, prior-week opposition,
  week-of-month, entry hour, MA **opposition** (not generic 5m MA-cross).
- Futures-native: overnight location/compression, prior RTH structure, OR15,
  VWAP, opening volume, ES/NQ/YM agreement, ST-age proxy, roll/holiday flags.

Artifacts: `condition_matrix.csv`, `candidate_ledger.csv`, `causal_feature_audit.csv`,
`*_campaigns.csv`, `SELECTED_BOOKS.json`.
