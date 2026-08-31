# NQ 15m RTH large-candle study

Universe: NQ Regular Trading Hours 09:30–16:00, **15-minute** candles resampled from `nq/nq_5min_rth.csv`.
Size = **high−low range**. Percentile = **causal expanding** of prior RTH 15m ranges (warmup 60 sessions; thresholds from history before the bar).

Trade: follow candle direction from **close**, SL at **open**, TP = **3× body**. Non-overlapping. Same-bar stop before target. Flatten 16:00. $1.50 fee, $20/pt.

| Metric | Value |
|---|---:|
| RTH 15m bars | 102,057 |
| Sessions | 3,986 |
| Bars ≥p90 | 32,945 (32.3%) |
| Days with ≥1 p90 | 3556 (89.2% of days) |
| Days with ≥1 p80 | 3857 (96.8% of days) |
| Chart sleeve | **p90** |
| Charts written | 214 / 3556 qualifying days (stratified sample: 50W/50L + yearly) |

Fair 3R WR with no edge ≈ **25%**. If large-candle WR sits near that (or below the all-candle book), size is not a directional signal.

## Books

| Book | n | WR | avg | net | stress | N/S | PF | avg R | tgt/stop/eod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p90 large 3R | 9853 | 29.2% | $16 | $160246 | $54069 | 2.96 | 1.05 | -0.04 | 1645/6601/1607 |
| p80 large 3R | 13501 | 27.7% | $10 | $136664 | $61188 | 2.23 | 1.04 | -0.08 | 2296/9354/1851 |
| p90 ATR-norm range 3R | 5499 | 32.7% | $29 | $160292 | $41104 | 3.90 | 1.09 | -0.01 | 790/3355/1354 |
| matched non-large control | 7012 | 22.7% | $-4 | $-26908 | $35498 | -0.76 | 0.95 | -0.16 | 1286/5343/383 |
| ALL directional 15m 3R (baseline) | 20699 | 25.4% | $6 | $123882 | $62297 | 1.99 | 1.03 | -0.11 | 3711/15059/1929 |

**Stance:** WR 29.2% vs fair ~25% 3R; N/S **2.96** vs non-large control −0.76 and all-15m 1.99. Size helps vs small candles (hour-9 and hour-15 carry most of the net). Still diagnostic — do not promote.

## Yearly (chart sleeve trades)

| Year | n | WR | net | N/S |
|---:|---:|---:|---:|---:|
| 2010 | 79 | 34.2% | $-2848 | -0.96 |
| 2011 | 467 | 34.9% | $5320 | 1.12 |
| 2012 | 268 | 33.6% | $1638 | 0.60 |
| 2013 | 255 | 34.9% | $6108 | 1.89 |
| 2014 | 484 | 31.0% | $4239 | 0.73 |
| 2015 | 641 | 29.5% | $-3826 | -0.37 |
| 2016 | 474 | 31.0% | $2419 | 0.36 |
| 2017 | 355 | 29.6% | $2018 | 0.30 |
| 2018 | 974 | 28.0% | $12074 | 0.74 |
| 2019 | 610 | 27.2% | $-5350 | -0.34 |
| 2020 | 1090 | 25.8% | $-11540 | -0.26 |
| 2021 | 867 | 27.9% | $-3356 | -0.18 |
| 2022 | 1064 | 29.1% | $86419 | 3.02 |
| 2023 | 612 | 30.6% | $14037 | 0.53 |
| 2024 | 702 | 29.2% | $40582 | 1.89 |
| 2025 | 766 | 27.9% | $-5349 | -0.11 |
| 2026 | 145 | 30.3% | $17662 | 0.79 |

## By NY hour (signal bar)

| Hour | n | WR | avg | net |
|---:|---:|---:|---:|---:|
| 9 | 3236 | 29.5% | $46 | $149426 |
| 10 | 2365 | 28.2% | $-17 | $-40372 |
| 11 | 1175 | 28.2% | $27 | $31162 |
| 12 | 830 | 26.4% | $-29 | $-24275 |
| 13 | 769 | 28.9% | $17 | $13226 |
| 14 | 987 | 30.8% | $1 | $600 |
| 15 | 491 | 37.3% | $62 | $30478 |

## Charts

Gold highlight = large candle (chart sleeve). Blue/purple markers = 3R entry/exit.
Index: [`charts/INDEX.md`](charts/INDEX.md).

Hub: `/home/tester/hsm/potions/live/state/nq_15m_large_candle`

