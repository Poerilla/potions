# USDJPY quarterly range honest breakout (broker-like)

Engine + PaperBroker on **USDJPY daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · USDJPY $100000/pt

## Results

- Combined net: **$2,378,716.00** (main $2,378,716.00)
- Trades: **112** (main 112)
- Stress DD (sum): **$-21,923,824.00**
- Net/|stress|: **0.11**

## Fill reasons

- `entry`: **112**
- `tp1`: **70**
- `flatten`: **54**
- `tp2`: **46**
- `tp3`: **39**
- `stop`: **33**
- `tp4`: **24**
