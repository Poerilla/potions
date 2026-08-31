# EURUSD quarterly range honest breakout (broker-like)

Engine + PaperBroker on **EURUSD daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · EURUSD $100000/pt

## Results

- Combined net: **$135,147.40** (main $135,147.40)
- Trades: **111** (main 111)
- Stress DD (sum): **$-212,851.60**
- Net/|stress|: **0.63**

## Fill reasons

- `entry`: **111**
- `tp1`: **67**
- `flatten`: **58**
- `tp2`: **45**
- `tp3`: **34**
- `stop`: **28**
- `tp4`: **24**
