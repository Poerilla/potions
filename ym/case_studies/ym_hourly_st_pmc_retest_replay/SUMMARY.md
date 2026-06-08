# YM Hourly ST + Prior Month Close Retest Replay

Strategy rules:
- Hourly `ATR(14) x 3` Supertrend on all available 1m sessions.
- If price is **above** prior calendar month close → long limit at bullish ST stop.
- If price is **below** prior calendar month close → short limit at bearish ST stop.
- Bracket: `50` pt stop / `150` pt target (3R). One trade at a time; limit re-armed when flat.
- Costs: $1.50/side, 1 tick stop slippage.

## Summary

- Trades: **903**
- Win rate: **42.3%** (382W / 521L)
- Net P/L: **$149,538.89**
- Profit factor: **2.10**
- Max closed drawdown: **$-3,897.00**
- Net / |DD|: **38.37**

## By side

- Longs: 527 trades, $78,802.51 net
- Shorts: 376 trades, $70,736.39 net
- Avg win: $747.00 | Avg loss: $-260.68

Full log: `trades.csv`
