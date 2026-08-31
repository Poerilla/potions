# NQ opening-candle close-limit 3R — HP condition mill

Diagnostic only — not a promotion gate. Built on **broker** fills (`open1h_close_limit_3r`), not pandas walk.

Contract: 1h opening candle → limit @ close → SL=open → TP=3R.

## Book

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| open1h_close_limit_3r | 3906 | 38.5% | $37 | $144,018 | $35,325 | 4.08 | 1.11 |

## Yearly

| Year | n | WR | net | N/S |
|---:|---:|---:|---:|---:|
| 2010 | 143 | 37.8% | $-3,104 | -0.71 |
| 2011 | 246 | 41.1% | $696 | 0.17 |
| 2012 | 243 | 35.8% | $549 | 0.15 |
| 2013 | 239 | 33.9% | $-4,048 | -0.48 |
| 2014 | 243 | 38.3% | $-1,431 | -0.21 |
| 2015 | 249 | 38.2% | $596 | 0.07 |
| 2016 | 251 | 35.9% | $-1,492 | -0.17 |
| 2017 | 248 | 34.3% | $-1,967 | -0.37 |
| 2018 | 249 | 38.2% | $13,296 | 2.01 |
| 2019 | 252 | 38.5% | $7,787 | 1.03 |
| 2020 | 246 | 35.8% | $-20,119 | -0.71 |
| 2021 | 248 | 42.7% | $10,668 | 0.91 |
| 2022 | 252 | 42.5% | $62,327 | 4.69 |
| 2023 | 247 | 38.5% | $24,900 | 2.81 |
| 2024 | 252 | 39.7% | $23,442 | 1.04 |
| 2025 | 253 | 43.1% | $36,350 | 1.96 |
| 2026 | 45 | 42.2% | $-4,432 | -0.32 |

## Top dual-lift notables (n≥40, WR+avg lift)

| Condition | Bucket | n | WR | WR lift | avg | avg lift | z_WR | N/S |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| First-hour body conviction | strong | 1084 | 51.2% | +12.7pp | $0 | $+69 | 7.63 | 3.66 |
| Large-candle vs PO side | candle_with_po | 238 | 48.3% | +9.9pp | $0 | $+247 | 3.04 | 3.29 |
| Trade side vs PO side | trade_with_po | 238 | 48.3% | +9.9pp | $0 | $+247 | 3.04 | 3.29 |
| PO regime | during_counter_with_po | 221 | 48.4% | +10.0pp | $0 | $+212 | 2.96 | 2.47 |
| First-hour range size | fh_p95 | 628 | 43.6% | +5.2pp | $0 | $+56 | 2.48 | 1.96 |
| First-hour range size | fh_p90 | 600 | 43.7% | +5.2pp | $0 | $+59 | 2.44 | 3.69 |
| Hourly RSI bucket | rsi_gt70 | 394 | 44.4% | +6.0pp | $0 | $+1 | 2.32 | 1.30 |
| PO v2b session state | during_po | 247 | 45.3% | +6.9pp | $0 | $+142 | 2.16 | 1.77 |
| Prior-week range half | week_opposed | 2213 | 40.8% | +2.4pp | $0 | $+17 | 1.82 | 3.82 |
| Hourly RSI vs trade | rsi_with_side | 2016 | 40.7% | +2.3pp | $0 | $+20 | 1.70 | 6.94 |
| Opening 15m direction vs trade | or_aligned | 2752 | 40.5% | +2.0pp | $0 | $+21 | 1.67 | 5.65 |
| First-hour vs prior day | above_pdh | 499 | 42.3% | +3.8pp | $0 | $+13 | 1.66 | 1.65 |
| OR15 vs first hour | or15_agree | 2739 | 40.5% | +2.0pp | $0 | $+21 | 1.65 | 5.69 |
| Day of week | Friday | 776 | 41.5% | +3.0pp | $0 | $+54 | 1.59 | 2.21 |
| Week of month | 4 | 884 | 41.3% | +2.8pp | $0 | $+67 | 1.57 | 6.38 |
| ATR14 quartile | atr_q4 | 974 | 40.9% | +2.4pp | $0 | $+60 | 1.38 | 3.54 |
| Month | 4 | 305 | 42.3% | +3.8pp | $0 | $+170 | 1.33 | 4.98 |
| Month | 12 | 328 | 41.8% | +3.3pp | $0 | $+29 | 1.19 | 1.27 |
| Prior RTH range percentile | prior_range_norm | 1192 | 40.4% | +1.9pp | $0 | $+34 | 1.18 | 2.96 |
| Overnight compression | on_norm | 1223 | 39.9% | +1.4pp | $0 | $+81 | 0.91 | 10.97 |
| Opening 15m volume percentile | vol_mid | 1219 | 39.9% | +1.4pp | $0 | $+54 | 0.89 | 6.87 |
| First-hour close location | lower | 1233 | 39.8% | +1.4pp | $0 | $+34 | 0.86 | 3.48 |
| Entry hour (NY) | 11 | 48 | 43.8% | +5.3pp | $0 | $+92 | 0.75 | 4.94 |
| ATR causal rolling percentile | atr_p75_100 | 1087 | 39.6% | +1.1pp | $0 | $+14 | 0.66 | 1.54 |
| Week of month | 1 | 874 | 39.5% | +1.0pp | $0 | $+31 | 0.56 | 2.68 |

## vs current NQ prior-opposed HP buckets

| Condition | Bucket | book n | book WR lift | book avg lift | PO WR lift |
|---|---|---:|---:|---:|---:|
| Opening 15m range vs ATR | or_norm | 1230 | -1.0pp | $+33 | 70.5% |
| ST-event age | st_age_30_90m | 3830 | -0.0pp | $+0 | 70.3% |
| NQ-ES dispersion | disp_mid | 1277 | -0.3pp | $+20 | 68.8% |
| Hourly RSI vs trade | rsi_against_side | 859 | -4.1pp | $-43 | 71.0% |
| 5m MA vs trade | ma_aligned | 3401 | +1.4pp | $+12 | 65.7% |
| ST-event direction vs trade | st_opposed_proxy | 0 | +0.0pp | $+0 | 71.0% |
| Week of month | 2 | 926 | -1.1pp | $-36 | 73.1% |
| Day of week | Friday | 776 | +3.0pp | $+54 | 68.2% |

## Stance

- Parent study: [`../SUMMARY.md`](../SUMMARY.md) — limit 1h **N/S 3.91** (works).
- HP notes are **hypotheses only**; do not size-up from this mill without nulls.
- Market-close twin remains stronger (N/S 5.57); limit is the fill-discipline variant.

Hub: `/home/tester/hsm/potions/live/state/nq_opening_candle_close_limit/hp`
