# XAGUSD quarterly range honest breakout (broker-like)

Engine + PaperBroker on **XAGUSD daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · XAGUSD $1000/pt

## Results

- Combined net: **$-182,896.20** (main $-182,896.20)
- Trades: **108** (main 108)
- Stress DD (sum): **$-456,024.00**
- Net/|stress|: **-0.40**

## Fill reasons

- `entry`: **108**
- `tp1`: **77**
- `tp2`: **50**
- `flatten`: **48**
- `tp3`: **40**
- `tp4`: **33**
- `stop`: **27**
