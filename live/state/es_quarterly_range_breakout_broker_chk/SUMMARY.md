# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt

## Results

- Combined net: **$827,692.00** (main $827,692.00)
- Trades: **74** (main 74)
- Stress DD (sum): **$-394,591.00**
- Net/|stress|: **2.10**

## Fill reasons

- `entry`: **74**
- `tp1`: **59**
- `flatten`: **47**
- `tp2`: **39**
- `tp3`: **23**
- `stop`: **15**
- `tp4`: **12**
