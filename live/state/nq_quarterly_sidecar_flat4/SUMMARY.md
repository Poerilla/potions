# NQ quarterly range honest breakout (broker-like)

Engine + PaperBroker on **NQ daily**.

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Mid-stop sidecar (separate position):** large prior width (causal p75); same risk magnitude; targets **1–2–3–4R**; EOQ → **flatten at EOQ**; runs independently of main (no blocking / no yield).
- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt

## Results

- Combined net: **$1,187,520.00** (main $1,438,818.00 + sidecar $-251,298.00)
- Trades: **89** (main 80 + sidecar 9)
- Stress DD (sum): **$-1,158,374.00**
- Net/|stress|: **1.03**

## Fill reasons

- `entry`: **80**
- `tp1`: **57**
- `flatten`: **57**
- `tp2`: **38**
- `tp3`: **24**
- `stop`: **21**
- `tp4`: **11**
- `sidecar_entry`: **9**
