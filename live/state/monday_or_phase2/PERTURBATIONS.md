# Monday OR Phase 2 — local perturbations

Narrow cells only (not a full re-sweep). Metrics from Phase 1 broker CSV.

| Pair | Tag | Role | ≈USD Net | Stress | **N/S** | Δ vs anchor N/S |
|---|---|---|---:|---:|---:|---:|
| EURUSD | `M1_S2_R2` | anchor | $+123271 | $-70858 | **1.74** | +0.00 |
| EURUSD | `M1_S2_R1` | EURUSD tighter R | $+78069 | $-82778 | **0.94** | -0.80 |
| USDJPY | `M2_S3_R1` | anchor | $+218890 | $-26688 | **8.20** | +0.00 |
| USDJPY | `M2_S3_R2` | USDJPY alt | $+227564 | $-27802 | **8.19** | -0.02 |
| USDJPY | `M2_S2_R1` | robustness | $+151778 | $-26801 | **5.66** | -2.54 |

## Read

- EURUSD `M1_S2_R1` (max 2/week) **hurts** N/S vs locked `R2` — keep max 3/week.
- USDJPY `M2_S3_R1` ≈ `M2_S3_R2` (8.20 vs 8.19) — retain R1 primary, R2 as dollar alt.
- USDJPY lighter sidecar `M2_S2_R1` (5.66) is weaker but still strong — heavy sidecar is the edge amplifier, not the whole edge.

*Generated from Phase 1 broker results.*
