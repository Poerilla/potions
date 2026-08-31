# NQ 15m RTH large-candle study (p99 / p95)

Universe: NQ Regular Trading Hours 09:30–16:00, **15-minute** candles resampled from `nq/nq_5min_rth.csv`.
Size = **high−low range**. Percentile = **causal expanding** of prior RTH 15m ranges (warmup 60 sessions; thresholds from history before the bar).
Primary sleeve **p99**; fallback **p95** if days with ≥1 p99 < 8% of sessions or p99 bars < 80.

Trade: follow candle direction from **close**, SL at **open**, TP = **3× body**. Non-overlapping. Same-bar stop before target. Flatten 16:00. $1.50 fee, $20/pt.

| Metric | Value |
|---|---:|
| RTH 15m bars | 102,057 |
| Sessions | 3,986 |
| Bars ≥p99 | 5,051 (4.9%) |
| Days with ≥1 p99 | 1432 (35.9% of days) |
| Bars ≥p95 | 19,512 |
| Days with ≥1 p95 | 3051 (76.5% of days) |
| Sleeve pick | **p99** |
| Charts written | 217 / 1432 qualifying days (stratified sample: 50W/50L + yearly) |

Fair 3R WR with no edge ≈ **25%**. If large-candle WR sits near that (or below the all-candle book), size is not a directional signal.

## Books

| Book | n | WR | avg | net | stress | N/S | PF | avg R | tgt/stop/eod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p99 large 3R | 2290 | 34.5% | $39 | $89540 | $58887 | 1.52 | 1.07 | 0.02 | 313/1343/634 |
| p95 large 3R | 6738 | 31.1% | $30 | $200863 | $45014 | 4.46 | 1.08 | -0.01 | 1086/4348/1304 |
| p99 ATR-norm range 3R | 992 | 39.0% | $89 | $88232 | $24450 | 3.61 | 1.21 | 0.08 | 115/477/400 |
| matched non-large control | 1981 | 26.2% | $17 | $33028 | $9942 | 3.32 | 1.13 | -0.07 | 382/1428/171 |
| ALL directional 15m 3R (baseline) | 20699 | 25.4% | $6 | $123882 | $62297 | 1.99 | 1.03 | -0.11 | 3711/15059/1929 |

**Stance:** curious lift vs fair 3R — still diagnostic; do not promote.

## Yearly (chart sleeve trades)

| Year | n | WR | net | N/S |
|---:|---:|---:|---:|---:|
| 2010 | 10 | 10.0% | $-2095 | -0.96 |
| 2011 | 87 | 32.2% | $-1596 | -0.44 |
| 2012 | 16 | 56.2% | $2561 | 5.81 |
| 2013 | 19 | 52.6% | $2852 | 4.53 |
| 2014 | 115 | 37.4% | $1188 | 0.38 |
| 2015 | 157 | 31.8% | $-5330 | -0.45 |
| 2016 | 104 | 38.5% | $2669 | 0.49 |
| 2017 | 55 | 45.5% | $8102 | 3.01 |
| 2018 | 337 | 36.2% | $36934 | 3.47 |
| 2019 | 87 | 35.6% | $7790 | 1.51 |
| 2020 | 353 | 30.0% | $1800 | 0.05 |
| 2021 | 185 | 34.1% | $-778 | -0.03 |
| 2022 | 316 | 34.8% | $46301 | 1.77 |
| 2023 | 50 | 44.0% | $1360 | 0.07 |
| 2024 | 117 | 34.2% | $4794 | 0.23 |
| 2025 | 235 | 30.2% | $-32512 | -0.55 |
| 2026 | 47 | 38.3% | $15500 | 1.10 |

## By NY hour (signal bar)

| Hour | n | WR | avg | net |
|---:|---:|---:|---:|---:|
| 9 | 990 | 33.8% | $16 | $15885 |
| 10 | 518 | 30.1% | $-53 | $-27617 |
| 11 | 192 | 33.9% | $84 | $16087 |
| 12 | 136 | 33.8% | $121 | $16431 |
| 13 | 129 | 42.6% | $253 | $32666 |
| 14 | 239 | 36.8% | $16 | $3926 |
| 15 | 86 | 51.2% | $374 | $32161 |

## Charts

Gold highlight = large candle (chart sleeve). Blue/purple markers = 3R entry/exit.
Index: [`charts/INDEX.md`](charts/INDEX.md).

Hub: `/home/tester/hsm/potions/live/state/nq_15m_large_candle_p99`

