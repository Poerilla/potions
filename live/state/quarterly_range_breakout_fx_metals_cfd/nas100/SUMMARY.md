# NAS100 quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NAS100 daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar:** off
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · NAS100 $1/pt

## Results

- Combined net: **$99,797.74** (main $99,797.74)
- Trades: **49** (main 49)
- Stress DD (sum): **$-24,303.12**
- Net/|stress|: **4.11**

## Fill reasons

- `entry`: **49**
- `flatten`: **33**
- `tp1`: **32**
- `tp2`: **22**
- `tp3`: **15**
- `stop`: **8**
- `tp4`: **7**
