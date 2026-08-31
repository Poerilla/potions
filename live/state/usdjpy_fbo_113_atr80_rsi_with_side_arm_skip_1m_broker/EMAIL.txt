# USDJPY FBO atr80 × rsi_with_side (long RSI≥55 / short RSI≤45) — arm-time skip_candidate (feed=1m)

Executable HA-near path: **arm-time** causal hourly rsi_with_side (long RSI≥55 / short RSI≤45) + atr80. On reject: **skip_candidate**. PaperBroker fills on **1m**; MTM audit on **4H**. Paper HA sleeve was post-hoc n=95 — not a target to reproduce exactly.

| Variant | Campaigns | WR | Net≈USD | Stress≈USD | N/S | Stance |
|---|---:|---:|---:|---:|---:|---|
| **arm skip_candidate (1m)** | 32 | 43.8% | **$-2053** | $-39610 | **-0.05** | reject |
| legacy date-gate 1m | 102 | 49.0%% | $58554 | $-43666 | 1.34 | weak |
| baseline atr80 daily | 156 | 50.6% | $107890 | — | 4.25 | banked |
| HA paper filter (post-hoc) | 95 | — | — | — | — | diagnostic |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi_with_side_arm_skip_1m_broker`
Filter atr80: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi_with_side_arm_skip_1m_broker/filters/usdjpy_atr80.csv`
Arm RSI CSV: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi_with_side_arm_skip_1m_broker/filters/usdjpy_hourly_rsi_causal.csv`
DSR: TRL-2026-00157
