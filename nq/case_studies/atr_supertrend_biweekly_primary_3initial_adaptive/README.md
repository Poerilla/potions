# NQ — Biweekly ATR Supertrend · Adaptive Scaling · 3-Initial

## Signal
Primary signal: **Biweekly ATR(14)×3.0 Supertrend** (2-week Friday-anchored bars, Wilder smoothing).
Long entry: next daily open after completed biweekly bar flips bullish.
Long exit : next daily open after completed biweekly bar flips bearish.

## Position Sizing — Adaptive Doubling Pyramid
- **Initial size**: 3 contracts.
- **Scaling unit** (= abs worst single-trade loss from weekly ATR strat): **$29,640**.
- Add 1 contract when total open PnL rises ≥ 1× unit above the PnL at the last add.
- Each subsequent interval doubles: 1× → 2× → 4× → 8× … × unit.
- Open PnL checked at daily close; add executed at that close.
- Hard cap: 20 contracts.

## Results

| # | Entry | Exit | Peak contracts | Adds | Net PnL | MAE | Duration |
|---|---|---|---|---|---:|---:|---:|
| #1 | 2012-02-05 | 2016-02-14 | 3→5 | 2 | $+114,870 | $5,160 | 1470d |
| #2 | 2016-12-18 | 2018-12-30 | 3→6 | 3 | $+81,650 | $39,620 | 742d |
| #3 | 2019-04-07 | 2020-03-22 | 3→5 | 2 | $-116,890 | $133,815 | 350d |
| #4 | 2020-05-17 | 2022-02-20 | 3→7 | 4 | $+480,295 | $26,220 | 644d |

**Total PnL**: $+559,925  |  **Win rate**: 3/4 (75%  |  **Max DD**: $-116,890

## vs Flat 3-Contract Baseline

| Metric | Flat 3c | Adaptive | Δ |
|---|---:|---:|---:|
| Total PnL | $+1,001,040 | $+559,925 | -44% |
| Max DD | $-48,585 | $-116,890 | -141% |

## Per-Trade Add Detail

### Trade #1  2012-02-05 → 2016-02-14  3→5c  net $+114,870

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2013-05-17 | 3025.75 | $30,360 | $59,280 |
| #2 | 2014-06-05 | 3779.0 | $90,620 | $118,560 |

### Trade #2  2016-12-18 → 2018-12-30  3→6c  net $+81,650

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2017-03-15 | 5421.75 | $30,360 | $59,280 |
| #2 | 2017-10-27 | 6214.5 | $93,780 | $118,560 |
| #3 | 2018-07-15 | 7407.5 | $213,080 | $237,120 |

### Trade #3  2019-04-07 → 2020-03-22  3→5c  net $-116,890

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2019-10-28 | 8113.0 | $30,315 | $59,280 |
| #2 | 2020-01-02 | 8898.25 | $93,135 | $118,560 |

### Trade #4  2020-05-17 → 2022-02-20  3→7c  net $+480,295

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2020-06-02 | 9675.25 | $32,415 | $59,280 |
| #2 | 2020-07-06 | 10640.0 | $109,595 | $118,560 |
| #3 | 2020-08-26 | 11967.5 | $242,345 | $237,120 |
| #4 | 2021-04-13 | 13966.75 | $482,255 | $474,240 |

## Key Observations
- Biweekly ATR fires ~5 signals per instrument over 15 years — extremely slow.
- Adaptive pyramid amplifies winners significantly (Trade 4 NQ: 3→7c, +$480K).
- Main risk: COVID losing trade (NQ 2019-2020) built to 5c before the flush → -$117K DD.
- No entry price guard in this baseline; adding one would reduce the COVID loss.
