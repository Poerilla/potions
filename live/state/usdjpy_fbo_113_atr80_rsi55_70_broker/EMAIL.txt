# USDJPY FBO 1/1/3 atr80 × RSI 55–70 (broker-like)

Banked FBO atr80 book with **entry_filter** = atr80 AND causal hourly RSI14 in [55, 70] (HA `rsi_55_70` bucket). Fee $7 / unit; daily Engine+PaperBroker.

| Variant | Campaigns | WR | Net≈USD | Stress≈USD | N/S | Stance |
|---|---:|---:|---:|---:|---:|---|
| **atr80 + RSI 55–70** | 102 | 49.0% | **$32941** | $-51867 | **0.64** | weak — prefer unfiltered atr80 |
| baseline atr80 only | 156 | 50.6% | $107890 | — | 4.25 | banked |
| HA filter overlay (paper) | 38 | ~68% | ~$91726 | — | — | diagnostic |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_broker`
Filter: `/home/tester/hsm/potions/live/state/usdjpy_fbo_113_atr80_rsi55_70_broker/filters/usdjpy_atr80_rsi55_70.csv`
DSR: TRL-2026-00152
