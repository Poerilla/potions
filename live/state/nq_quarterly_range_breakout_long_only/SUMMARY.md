# NQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NQ daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt · tick 0.25

## Results

- Trades: **54**
- Units: **432**
- Net: **$1,462,736.00**
- Closed DD: **$-458,152.00**
- Stress DD: **$-477,472.00**
- Net/|stress|: **3.06**
- Win units: **302** / Loss units: **130**

## Fill reasons

- `entry`: **54**
- `tp1`: **36**
- `flatten`: **36**
- `tp2`: **27**
- `tp3`: **17**
- `stop`: **10**
- `tp4`: **8**

## Files

- `states/nq_quarterly_range_breakout_long_only/fills.csv`
- `audits/`
