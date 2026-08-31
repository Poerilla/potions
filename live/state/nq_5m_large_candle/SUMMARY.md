# NQ 5m RTH large-candle study

Universe: NQ Regular Trading Hours 09:30–16:00, 5-minute candles (`nq/nq_5min_rth.csv`).
Size = **high−low range**. Percentile = **causal expanding** of prior RTH 5m ranges (warmup 60 sessions; thresholds from history before the bar).

Trade: follow candle direction from **close**, SL at **open**, TP = **3× body**. Non-overlapping. Same-bar stop before target. Flatten 16:00. $1.50 fee, $20/pt.

| Metric | Value |
|---|---:|
| RTH 5m bars | 306,160 |
| Sessions | 3,986 |
| Bars ≥p90 | 98,719 (32.2%) |
| Days with ≥1 p90 | 3836 (96.2% of days) |
| Days with ≥1 p80 | 3944 (98.9% of days) |
| Chart sleeve | **p90** |
| Charts written | 211 / 3836 qualifying days (stratified sample: 50W/50L + yearly) |

Fair 3R WR with no edge ≈ **25%**. If large-candle WR sits near that (or below the all-candle book), size is not a directional signal.

## Books

| Book | n | WR | avg | net | stress | N/S | PF | avg R | tgt/stop/eod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p90 large 3R | 25551 | 25.6% | $5 | $116518 | $86464 | 1.35 | 1.02 | -0.05 | 5402/18741/1408 |
| p80 large 3R | 36392 | 24.4% | $0 | $10757 | $134086 | 0.08 | 1.00 | -0.08 | 7624/27198/1570 |
| p90 ATR-norm range 3R | 13311 | 29.2% | $15 | $205964 | $74770 | 2.75 | 1.07 | -0.00 | 2600/9094/1617 |
| matched non-large control | 19289 | 20.6% | $-6 | $-120168 | $122301 | -0.98 | 0.88 | -0.19 | 3778/15283/228 |
| ALL directional 5m 3R (baseline) | 59657 | 22.4% | $-3 | $-180010 | $282521 | -0.64 | 0.97 | -0.14 | 12158/46009/1490 |

**Stance:** WR near fair 3R — size does not mean follow-through.

## Yearly (chart sleeve trades)

| Year | n | WR | net | N/S |
|---:|---:|---:|---:|---:|
| 2010 | 166 | 34.3% | $1056 | 0.72 |
| 2011 | 1211 | 28.0% | $5684 | 1.56 |
| 2012 | 661 | 29.7% | $1788 | 0.52 |
| 2013 | 613 | 34.7% | $11950 | 8.17 |
| 2014 | 1270 | 28.3% | $12485 | 4.42 |
| 2015 | 1743 | 24.8% | $-15234 | -0.78 |
| 2016 | 1225 | 27.9% | $8378 | 1.74 |
| 2017 | 920 | 27.3% | $8295 | 2.02 |
| 2018 | 2565 | 24.1% | $10952 | 0.59 |
| 2019 | 1559 | 24.3% | $-7274 | -0.43 |
| 2020 | 2911 | 24.1% | $-12446 | -0.24 |
| 2021 | 2195 | 24.7% | $-2352 | -0.07 |
| 2022 | 2843 | 23.2% | $-18740 | -0.38 |
| 2023 | 1505 | 26.8% | $16002 | 0.49 |
| 2024 | 1832 | 25.2% | $21207 | 0.69 |
| 2025 | 1961 | 25.2% | $79094 | 1.97 |
| 2026 | 371 | 24.8% | $-4326 | -0.16 |

## By NY hour (signal bar)

| Hour | n | WR | avg | net |
|---:|---:|---:|---:|---:|
| 9 | 6450 | 26.6% | $37 | $238055 |
| 10 | 5466 | 24.4% | $-8 | $-43179 |
| 11 | 3449 | 25.1% | $12 | $41682 |
| 12 | 2530 | 24.4% | $-21 | $-53680 |
| 13 | 2450 | 24.9% | $-3 | $-8045 |
| 14 | 2858 | 26.2% | $-11 | $-32492 |
| 15 | 2348 | 27.6% | $-11 | $-25822 |

## Charts

Gold highlight = large candle (chart sleeve). Blue/purple markers = 3R entry/exit.
Index: [`charts/INDEX.md`](charts/INDEX.md).

Hub: `/home/tester/hsm/potions/live/state/nq_5m_large_candle`

