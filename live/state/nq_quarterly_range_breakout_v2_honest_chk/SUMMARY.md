# NQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NQ daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt

## Results

- Combined net: **$1,438,818.00** (main $1,438,818.00)
- Trades: **80** (main 80)
- Stress DD (sum): **$-505,462.00**
- Net/|stress|: **2.85**

## Fill reasons

- `entry`: **80**
- `tp1`: **53**
- `flatten`: **51**
- `tp2`: **37**
- `tp3`: **24**
- `stop`: **18**
- `tp4`: **11**
