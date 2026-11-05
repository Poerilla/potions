# TOP3 joint 1-minute broker portfolio (Clean Break ×10)

Shared minute clock over Engine+PaperBroker fills from the three active demos.
Lots stay strategy-scoped (no cross-sleeve fill interference). NAS100 Clean Break **×10**.

## Common window

| | |
|---|---|
| Start | 2016-11-15 |
| End | 2025-09-29 |
| Joint net | $355639.98 |
| Joint close MTM DD | $-33438.40 |
| **Joint intrabar stress DD** | **$-33525.68** |
| **True common-window N/S** | **10.61** |
| Max open units | 14 |
| 1m events walked | 4,175,840 |

## Sleeve nets on common-window entries (CB×10)

| Sleeve | Units | Trades | Net |
|---|---:|---:|---:|
| Asia Range | 4228 | 604 | $127288.22 |
| Monday OR | 2414 | 751 | $105822.26 |
| Clean Break ×10 | 2070 | 1166 | $122529.50 |

## Method

- Asia: `v2b_scaleout` S_3_1_3_flt fills → mark on USDJPY 1m
- Monday OR: `monday_or_breakout` M2_S3_R1 skip Aug/Sep fills → mark on USDJPY 1m
- Clean Break: `v2b_clean_break` trail06_m4_e2_out_be 1m-fill tape → mark on NAS100 1m, size ×10
- Joint close / intrabar equity = sum of sleeve MTMs each minute (JPY÷110)

Artifacts: `equity_curve_1m_sample.csv` (every 5th minute), `equity_curve_daily.csv`, `metrics.json`.
