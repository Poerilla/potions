# CHOP20 Range Breakout Study - NQ / YM

Daily, causal range detector based on CHOP(20), directional efficiency, and 20-day range width normalized by ATR(20). This is a detection/chart pack, not a broker replay or promoted trading system.

## Detector

| Parameter | Value |
|---|---:|
| `range_lookback` | 20 |
| `atr_lookback` | 20 |
| `baseline_lookback` | 252 |
| `chop_range_threshold` | 61.8 |
| `chop_trend_threshold` | 38.2 |
| `efficiency_range_max` | 0.35 |
| `efficiency_trend_min` | 0.55 |
| `width_pctl_low` | 0.2 |
| `width_pctl_high` | 0.8 |
| `confirm_days` | 2 |
| `min_history` | 252 |
| `max_wait_trading_days` | 252 |

## Causality

- All regime features are calculated from completed daily candles.
- Range width percentile compares the current value only to prior completed values.
- A range segment is known after its final completed daily close.
- Breakout detection uses the first later completed daily close outside the frozen box.
- Charts intentionally run one year forward from each breakout and do not stop when a later range appears.

## Markets

| Market | Coverage | Bars | Range segments | Breakouts | Up / Down | Median wait | Index |
|---|---|---:|---:|---:|---:|---:|---|
| NQ | 2010-06-06 to 2026-03-08 | 4,887 | 38 | 37 | 23/14 | 1.0 | [NQ](./nq/INDEX.md) |
| YM | 2010-06-06 to 2026-05-06 | 4,942 | 41 | 41 | 28/13 | 1.0 | [YM](./ym/INDEX.md) |

## Outputs

- `summary.csv`
- `{market}/daily_regimes.csv`
- `{market}/range_segments.csv`
- `{market}/range_breakouts.csv`
- `{market}/charts/*.png`
