# QQQ / SQQQ Slow OBV Overlay

Visual study: QQQ and SQQQ plotted together with slow OBV cross markers.

- `SQQQ` is used as the inverse leveraged QQQ proxy (3x daily-reset inverse Nasdaq-100 ETF).
- Prices are Yahoo adjusted closes, normalized to the first common trading day, and plotted on a log scale.
- Slow OBV cross uses OBV crossing its `200`-day simple moving average.
- Markers: QQQ bearish OBV crosses and SQQQ bullish OBV crosses.
- SQQQ is a daily-reset leveraged ETF; the long-term line includes leverage decay and reverse split adjustments.

Window: **2010-02-11 through 2026-06-01**.

## Summary

| Ticker | Start Close | End Close | Adj Close Return | Bull Crosses | Bear Crosses | Bull / Yr | Bear / Yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| QQQ | $38 | $743 | 1859.54% | 93 | 92 | 5.71 | 5.64 |
| SQQQ | $9,539,202 | $37 | -100.00% | 93 | 93 | 5.71 | 5.71 |

## Cross Alignment

- QQQ bearish crosses: **92**.
- SQQQ bullish crosses: **93**.
- QQQ bearish crosses with a SQQQ bullish cross within 3 calendar days: **36**.
- QQQ bearish crosses with a SQQQ bullish cross within 5 calendar days: **42**.

## Charts

- Full common history: [`charts/qqq_sqqq_slow_obv_full.png`](charts/qqq_sqqq_slow_obv_full.png)
- Recent zoom: [`charts/qqq_sqqq_slow_obv_recent.png`](charts/qqq_sqqq_slow_obv_recent.png)

## Outputs

- `summary.csv`
- `QQQ_slow_obv_daily.csv`
- `SQQQ_slow_obv_daily.csv`
