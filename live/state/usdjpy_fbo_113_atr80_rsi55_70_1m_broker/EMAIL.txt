# USDJPY FBO 1/1/3 atr80 × RSI 55–70 (broker-like, feed=1m)

Entry filter = atr80 AND causal hourly RSI14 in [55, 70]. OR / decisions remain **daily** (NY); PaperBroker fills on **1m**. MTM audit on **4H**.

| Variant | Campaigns | WR | Net≈USD | Stress≈USD | N/S | Stance |
|---|---:|---:|---:|---:|---:|---|
| **atr80 + RSI 55–70 (1m)** | 102 | 49.0% | **$58554** | $-43666 | **1.34** | weak — prefer unfiltered atr80 |
| baseline atr80 daily | 156 | 50.6% | $107890 | — | 4.25 | banked |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_1m_broker`
Filter: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_1m_broker/filters/usdjpy_atr80_rsi55_70.csv`
DSR: TRL-2026-00153
