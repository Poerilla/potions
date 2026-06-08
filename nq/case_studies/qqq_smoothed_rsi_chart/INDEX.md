# QQQ Smoothed RSI Chart

Data: Yahoo adjusted daily OHLCV for `QQQ`.
Window: **2000-01-01 through 2026-06-02**.

Indicator:

- RSI uses Wilder-style RSI(14).
- Smoothed RSI is EMA(14) of RSI(14).
- Overbought/oversold reference bands are 70 / 30.

Latest completed row: **2026-06-02**.

| Close | RSI14 | Smoothed RSI | State |
|---:|---:|---:|---|
| 746.16 | 79.37 | 75.38 | overbought |

## Charts

- Full history: [`charts/qqq_smoothed_rsi_full.png`](charts/qqq_smoothed_rsi_full.png)
- Recent zoom: [`charts/qqq_smoothed_rsi_recent.png`](charts/qqq_smoothed_rsi_recent.png)

## Files

- `QQQ_smoothed_rsi_daily.csv`
