# NQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NQ daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt

## Results

- Combined net: **$1,411,432.00** (main $1,411,432.00)
- Trades: **63** (main 63)
- Stress DD (sum): **$-477,472.00**
- Net/|stress|: **2.96**

## Fill reasons

- `entry`: **63**
- `flatten`: **44**
- `tp1`: **41**
- `tp2`: **28**
- `tp3`: **18**
- `stop`: **10**
- `tp4`: **9**
