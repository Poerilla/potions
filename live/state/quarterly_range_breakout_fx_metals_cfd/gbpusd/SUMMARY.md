# GBPUSD quarterly range honest breakout (broker-like)

Engine + PaperBroker on **GBPUSD daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · GBPUSD $100000/pt

## Results

- Combined net: **$312,051.60** (main $312,051.60)
- Trades: **102** (main 102)
- Stress DD (sum): **$-200,612.00**
- Net/|stress|: **1.56**

## Fill reasons

- `entry`: **102**
- `tp1`: **69**
- `flatten`: **60**
- `tp2`: **44**
- `tp3`: **32**
- `tp4`: **23**
- `stop`: **19**
