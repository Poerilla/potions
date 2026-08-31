# AUDJPY quarterly range honest breakout (broker-like)

Engine + PaperBroker on **AUDJPY daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · AUDJPY $100000/pt

## Results

- Combined net: **$-26,352,176.00** (main $-26,352,176.00)
- Trades: **118** (main 118)
- Stress DD (sum): **$-38,618,688.00**
- Net/|stress|: **-0.68**

## Fill reasons

- `entry`: **118**
- `tp1`: **73**
- `flatten`: **62**
- `tp2`: **47**
- `tp3`: **33**
- `stop`: **30**
- `tp4`: **25**
