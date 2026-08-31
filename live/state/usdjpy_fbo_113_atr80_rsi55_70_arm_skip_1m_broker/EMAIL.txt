# USDJPY FBO atr80 × RSI 55–70 — arm-time skip_candidate (feed=1m)

Executable HA-near path: **arm-time** causal hourly RSI∈[55,70] + atr80. On reject: **skip_candidate**. PaperBroker fills on **1m**; MTM audit on **4H**. Paper HA sleeve was post-hoc n=38 — not a target to reproduce exactly.

| Variant | Campaigns | WR | Net≈USD | Stress≈USD | N/S | Stance |
|---|---:|---:|---:|---:|---:|---|
| **arm skip_candidate (1m)** | 57 | 47.4% | **$-1341** | $-46414 | **-0.03** | reject |
| legacy date-gate 1m | 102 | 49.0%% | $58554 | $-43666 | 1.34 | weak |
| baseline atr80 daily | 156 | 50.6% | $107890 | — | 4.25 | banked |
| HA paper filter (post-hoc) | 38 | ~68%% | ~$92k | — | — | diagnostic |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_arm_skip_1m_broker`
Filter atr80: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_arm_skip_1m_broker/filters/usdjpy_atr80.csv`
Arm RSI CSV: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_arm_skip_1m_broker/filters/usdjpy_hourly_rsi_causal.csv`
DSR: TRL-2026-00155
