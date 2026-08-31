# XAUUSD quarterly range honest breakout (broker-like)

Engine + PaperBroker on **XAUUSD daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · XAUUSD $100/pt

## Results

- Combined net: **$1,141,869.40** (main $1,141,869.40)
- Trades: **113** (main 113)
- Stress DD (sum): **$-614,031.60**
- Net/|stress|: **1.86**

## Fill reasons

- `entry`: **113**
- `tp1`: **82**
- `flatten`: **64**
- `tp2`: **57**
- `tp3`: **43**
- `tp4`: **30**
- `stop`: **19**
