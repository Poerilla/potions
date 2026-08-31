# CHOP20 Range Breakout Study - NQ / YM

Causal range detector based on CHOP(20), directional efficiency, and 20-bar range width normalized by ATR(20). This is a detection/chart pack, not a broker replay or promoted trading system.

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
| `max_wait_bars` | 252 |

## Causality

- All regime features are calculated from completed candles.
- Range width percentile compares the current value only to prior completed values.
- A range segment is known after its final completed candle close.
- Breakout detection uses the first later completed candle close outside the frozen box.
- Charts intentionally run one year forward from each breakout and do not stop when a later range appears.

## Markets

| Timeframe | Market | Coverage | Bars | Range segments | Breakouts | Charts | Up / Down | Median wait | Index |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 4h | NQ | 2010-06-06T16:00:00-04:00 to 2026-06-16T16:00:00-04:00 | 25,531 | 150 | 150 | 50 | 95/55 | 2.0 | [NQ](./4h/nq/INDEX.md) |
| 4h | YM | 2010-06-06T16:00:00-04:00 to 2026-05-06T16:00:00-04:00 | 25,378 | 180 | 180 | 50 | 98/82 | 1.0 | [YM](./4h/ym/INDEX.md) |
| 1h | NQ | 2010-06-07T09:00:00-04:00 to 2026-06-16T15:00:00-04:00 | 28,455 | 188 | 188 | 50 | 106/82 | 1.5 | [NQ](./1h/nq/INDEX.md) |
| 1h | YM | 2010-06-07T09:00:00-04:00 to 2026-05-06T15:00:00-04:00 | 28,286 | 196 | 196 | 50 | 114/82 | 1.0 | [YM](./1h/ym/INDEX.md) |

## Outputs

- `summary.csv`
- `{timeframe}/{market}/bar_regimes.csv`
- `{timeframe}/{market}/range_segments.csv`
- `{timeframe}/{market}/range_breakouts.csv`
- `{timeframe}/{market}/charts/*.png`
