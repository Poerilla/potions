# MNQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **MNQ daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · MNQ $2/pt · tick 0.25

## Results

- Trades: **31**
- Units: **248**
- Net: **$120,542.00**
- Closed DD: **$-50,365.00**
- Stress DD: **$-50,573.00**
- Net/|stress|: **2.38**
- Win units: **164** / Loss units: **84**

## Fill reasons

- `entry`: **31**
- `flatten`: **22**
- `tp1`: **21**
- `tp2`: **15**
- `tp3`: **8**
- `stop`: **7**
- `tp4`: **2**

## Files

- `states/mnq_quarterly_range_breakout/fills.csv`
- `audits/`
