# Monday OR Phase 2 — DD threshold sensitivity

Nudges around 30%/50% on locked size tags only. Pass if net > 0 and N/S drop ≤ ~30% vs anchor.

| Pair | Tag | Slug | DD | ≈USD Net | Stress | **N/S** | Δ N/S | Pass |
|---|---|---|---|---:|---:|---:|---:|---|
| AUDJPY | `M1_S2_R2` | anchor_30_50 | 30/50 | $+95822 | $-52242 | **1.83** | +0% | yes |
| AUDJPY | `M1_S2_R2` | dd25_45 | 25/45 | $+78231 | $-49063 | **1.59** | -13% | yes |
| AUDJPY | `M1_S2_R2` | dd35_55 | 35/55 | $+128457 | $-55485 | **2.32** | +26% | yes |
| EURUSD | `M1_S2_R2` | anchor_30_50 | 30/50 | $+123271 | $-70858 | **1.74** | +0% | yes |
| EURUSD | `M1_S2_R2` | dd25_45 | 25/45 | $+142361 | $-60563 | **2.35** | +35% | yes |
| EURUSD | `M1_S2_R2` | dd35_55 | 35/55 | $+102368 | $-54702 | **1.87** | +8% | yes |
| GBPUSD | `M1_S1_R2` | anchor_30_50 | 30/50 | $+231279 | $-86616 | **2.67** | +0% | yes |
| GBPUSD | `M1_S1_R2` | dd25_45 | 25/45 | $+234107 | $-95723 | **2.45** | -8% | yes |
| GBPUSD | `M1_S1_R2` | dd35_55 | 35/55 | $+259305 | $-93915 | **2.76** | +3% | yes |
| USDJPY | `M2_S3_R1` | anchor_30_50 | 30/50 | $+218890 | $-26688 | **8.20** | +0% | yes |
| USDJPY | `M2_S3_R1` | dd25_45 | 25/45 | $+208999 | $-31757 | **6.58** | -20% | yes |
| USDJPY | `M2_S3_R1` | dd35_55 | 35/55 | $+225419 | $-27240 | **8.28** | +1% | yes |
| XAUUSD | `M2_S2_R3` | anchor_30_50 | 30/50 | $+437940 | $-230359 | **1.90** | +0% | yes |
| XAUUSD | `M2_S2_R3` | dd25_45 | 25/45 | $+382005 | $-246558 | **1.55** | -19% | yes |
| XAUUSD | `M2_S2_R3` | dd35_55 | 35/55 | $+402718 | $-243249 | **1.66** | -13% | yes |

*Driver: `live/monday_or_phase2_robustness.py`.*
