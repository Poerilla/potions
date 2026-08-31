# NQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NQ daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar (separate position):** large prior width (causal p75); same risk magnitude; targets **1–2–3–4R**; EOQ → **BE carry** (no flatten); runs independently of main (no blocking / no yield).
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt

## Results

- Combined net: **$1,747,735.00** (main $1,438,818.00 + sidecar $308,917.00)
- Trades: **89** (main 80 + sidecar 9)
- Stress DD (sum): **$-1,158,374.00**
- Net/|stress|: **1.51**

## Fill reasons

- `entry`: **80**
- `tp1`: **58**
- `flatten`: **51**
- `tp2`: **42**
- `tp3`: **28**
- `stop`: **23**
- `tp4`: **15**
- `sidecar_entry`: **9**
