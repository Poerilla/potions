# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar (separate position):** large prior width (causal p75); same risk magnitude; targets **1R–4R**; EOQ → **BE carry** (no flatten); runs independently of main (no blocking / no yield).
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt

## Results

- Combined net: **$780,046.00** (main $827,692.00 + sidecar $-47,646.00)
- Trades: **82** (main 74 + sidecar 8)
- Stress DD (sum): **$-734,447.00**
- Net/|stress|: **1.06**

## Fill reasons

- `entry`: **74**
- `tp1`: **61**
- `flatten`: **47**
- `tp2`: **41**
- `tp3`: **24**
- `stop`: **22**
- `tp4`: **13**
- `sidecar_entry`: **8**
