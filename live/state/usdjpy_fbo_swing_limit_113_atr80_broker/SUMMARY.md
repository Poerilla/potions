# USDJPY FBO swing-limit 1/1/3 atr80 (broker-like)

Ignore first OR break → wait for **confirmed 3-bar swing** (high after ORH break / low after ORL break) → **limit** fade at the pivot. Absolute FBO targets from OR boundary (0.25R / 1R / 2R); stop **1R** beyond fill; BE after TP25; atr80; fee $7.

| Variant | Trades | Units | Net≈USD | Stress≈USD | N/S | Stance |
|---|---:|---:|---:|---:|---:|---|
| **swing-limit 1/1/3 atr80** | 185 | 925 | **$-49710** | $-152397 | **-0.33** | reject |
| baseline stop@opposite OR 1/1/3 atr80 | — | — | $107890 | — | 4.25 | banked |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_fbo_swing_limit_113_atr80_broker`
DSR: TRL-2026-00151
