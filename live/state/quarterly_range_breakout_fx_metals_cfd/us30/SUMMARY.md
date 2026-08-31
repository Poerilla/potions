# US30 quarterly range honest breakout (broker-like)

Engine + PaperBroker on **US30 daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · US30 $1/pt

## Results

- Combined net: **$72,814.56** (main $72,814.56)
- Trades: **48** (main 48)
- Stress DD (sum): **$-60,842.84**
- Net/|stress|: **1.20**

## Fill reasons

- `entry`: **48**
- `tp1`: **35**
- `tp2`: **25**
- `flatten`: **24**
- `tp3`: **15**
- `stop`: **14**
- `tp4`: **9**
