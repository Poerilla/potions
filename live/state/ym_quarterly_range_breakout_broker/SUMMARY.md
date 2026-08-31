# YM quarterly range honest breakout (broker-like)

Engine + PaperBroker on **YM daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · YM $5/pt · tick 1

## Results

- Trades: **69**
- Units: **552**
- Net: **$337,384.00**
- Closed DD: **$-215,956.00**
- Stress DD: **$-217,816.00**
- Net/|stress|: **1.55**
- Win units: **332** / Loss units: **220**

## Fill reasons

- `entry`: **69**
- `tp1`: **49**
- `flatten`: **35**
- `tp2`: **30**
- `stop`: **23**
- `tp3`: **17**
- `tp4`: **11**

## Files

- `states/ym_quarterly_range_breakout/fills.csv`
- `audits/`
