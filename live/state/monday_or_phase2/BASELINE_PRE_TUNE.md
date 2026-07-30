# Monday OR — pre-tune broker baselines (Phase 1 StrategyPlugin)

These are the **last locked Engine + PaperBroker** numbers **before** cluster/skip
tune-ups. MTM DD = intrabar mark-to-market drawdown (`stress_usd_approx`).

| Pair | Tag | Net ≈$ | MTM DD ≈$ | N/S | Units |
|---|---|---:|---:|---:|---:|
| USDJPY | M2_S3_R1 | +218,890 | −26,688 | **8.20** | 7700 |
| USDJPY | M2_S3_R2 | +227,564 | −27,802 | **8.19** | 9151 |
| EURUSD | M1_S2_R2 | +123,271 | −70,858 | **1.74** | 8290 |
| GBPUSD | M1_S1_R2 | +231,279 | −86,616 | **2.67** | 8739 |
| AUDJPY | M1_S2_R2 | +95,822 | −52,242 | **1.83** | 8045 |
| XAUUSD | M2_S2_R3 | +437,940 | −230,359 | **1.90** | 12139 |

## Locked core (post 2026-07-28 tune-ups)

| Pair | Tag | Knob(s) | Broker N/S | Net ≈$ |
|---|---|---|---:|---:|
| USDJPY | M2_S3_R1 | sitout +3 + skip Aug/Sep | **10.60** | +294k |
| USDJPY | M2_S3_R2 | skip-1-after-2W + skip Aug/Sep | **10.62** | +300k |
| XAUUSD | M2_S2_R3 | sitout +100 + skip Jul/Sep/Dec | **3.37** | +580k |

EURUSD / GBPUSD / AUDJPY skip candidates were **rejected** or not broker-locked.

Details: `CORE_WEEK_SITOUT.md`, `tuneup_broker/SUMMARY.md`.

Year-by-year (net, DD, Sharpe, Sortino, Calmar, WR, PF): [`yearly_core_vs_baseline/YEARLY_CORE_VS_BASELINE.md`](yearly_core_vs_baseline/YEARLY_CORE_VS_BASELINE.md).
