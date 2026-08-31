# NQ quarterly breakout — pyramid on DD, mid SL, uncapped winners

Engine + PaperBroker on **NQ daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout close outside prior Q → market **2**.
- **Add 2** every 0.2/0.4/0.6/0.8 × 179 pts adverse (max **10**).
- **SL** = prior-range **mid** (full position). No BE.
- **No profit targets** — winners run to mid stop or EOQ flatten.
- Add levels beyond mid are skipped.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt

## Results

- Trades: **69**
- Units: **138**
- Net: **$233,473.00**
- Closed DD: **$-178,704.00**
- Stress DD: **$-182,194.00**
- Net/|stress|: **1.28**
- Win units: **76** / Loss units: **62**

## Fill reasons

- `entry`: **69**
- `add1`: **60**
- `flatten`: **51**
- `add2`: **49**
- `add3`: **48**
- `add4`: **42**
- `stop`: **20**

## Files

- `states/nq_quarterly_range_breakout/fills.csv`
- `audits/`
