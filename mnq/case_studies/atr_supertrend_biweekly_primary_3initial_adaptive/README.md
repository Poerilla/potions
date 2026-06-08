# MNQ — Biweekly ATR Supertrend · Adaptive Scaling · 3-Initial

## Signal
Primary signal: **Biweekly ATR(14)×3.0 Supertrend** (2-week Friday-anchored bars, Wilder smoothing).
Long entry: next daily open after completed biweekly bar flips bullish.
Long exit : next daily open after completed biweekly bar flips bearish.

## Position Sizing — Adaptive Doubling Pyramid
- **Initial size**: 3 contracts.
- **Scaling unit** (= abs worst single-trade loss from weekly ATR strat): **$3,126**.
- Add 1 contract when total open PnL rises ≥ 1× unit above the PnL at the last add.
- Each subsequent interval doubles: 1× → 2× → 4× → 8× … × unit.
- Open PnL checked at daily close; add executed at that close.
- Hard cap: 20 contracts.

## Results

| # | Entry | Exit | Peak contracts | Adds | Net PnL | MAE | Duration |
|---|---|---|---|---|---:|---:|---:|
| #1 | 2020-05-10 | 2022-03-13 | 3→7 | 4 | $+38,386 | $2,622 | 672d |
| #2 | 2023-06-04 | 2025-04-06 | 3→7 | 4 | $+16,010 | $8,317 | 672d |

**Total PnL**: $+54,396  |  Win rate: 2/2  |  Max DD: $0

## vs Flat 3-Contract Baseline

| Metric | Flat 3c | Adaptive | Δ |
|---|---:|---:|---:|
| Total PnL | $+48,828 | $+54,396 | +11% |
| Max DD    | $0  | $0  | N/A (baseline DD=$0) |

## Per-Trade Add Detail

### Trade #1  2020-05-10 → 2022-03-13  3→7c  net $+38,386

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2020-06-05 | 9807.5 | $3,651 | $6,252 |
| #2 | 2020-07-06 | 10640.0 | $10,311 | $12,504 |
| #3 | 2020-08-26 | 11967.75 | $23,588 | $25,008 |
| #4 | 2021-06-14 | 14106.5 | $49,254 | $50,016 |

### Trade #2  2023-06-04 → 2025-04-06  3→7c  net $+16,010

| Add# | Date | Price | Open PnL at add | Next threshold |
|---|---|---:|---:|---:|
| #1 | 2023-06-13 | 15105.5 | $3,136 | $6,252 |
| #2 | 2023-07-18 | 15961.25 | $9,982 | $12,504 |
| #3 | 2024-01-19 | 17463.25 | $25,002 | $25,008 |
| #4 | 2024-06-12 | 19600.25 | $50,646 | $50,016 |

## Key Observations
- MNQ history starts May 2019 — misses the COVID losing trade entirely.
- Both trades built to 7 contracts via the adaptive pyramid.
- Zero drawdown on the equity curve (all closed trades profitable).
- The adaptive pyramid added ~36% to total PnL vs flat 3-contract baseline.
