# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt · tick 0.25

## Results

- Trades: **60**
- Units: **480**
- Net: **$1,258,367.50**
- Closed DD: **$-221,284.00**
- Stress DD: **$-225,184.00**
- Net/|stress|: **5.59**
- Win units: **364** / Loss units: **116**

## Fill reasons

- `entry`: **60**
- `tp1`: **52**
- `flatten`: **36**
- `tp2`: **34**
- `tp3`: **19**
- `stop`: **12**
- `tp4`: **12**

## Files

- `states/es_quarterly_range_breakout/fills.csv`
- `audits/`
