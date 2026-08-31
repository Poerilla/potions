# Expansion atlas — NQ structure-change event study

Frozen engine: `StructureProgramEngine_v1_existing`. Primary TF: **4h**. Penetration primary cut: **0.05 ATR** (zero-buffer rows tagged `min_pen_ATR=0`).

Holdout: most recent **25%** of events (`slice=holdout`). Tables below = **dev** unless noted.

**Outcome direction (audit fix):** CLOSE_BREAK = break dir; WICK_REJECT / CLOSE_RECLAIM = opposite of breach; TOUCH_ONLY = absolute excursion (no directional hypothesis).

**1R unit (primary tables):** structure-TF `ATR_20`. Structural-stop R companion table below; full denominator diagnostics in `OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md`.

**Time to 1R:** median minutes to first 1× unit favorable move inside the *two-session* window (not the 60m hit-rate). CSV also has `time_to_1R_within_60m_*`.

## Phase 1 — event class vs matched controls (4h, invalidation family, pen≥0.05, ATR R)

| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLOSE_BREAK | 126 | 0.022 | 0.056 | 0.0% | 1.6% | 0.0% | 0.56 | 0.56 | 1302 |
| WICK_REJECT | 95 | 0.000 | 0.010 | 0.0% | 2.1% | 3.2% | 0.63 | 0.58 | 1158 |
| CLOSE_RECLAIM | 46 | -0.054 | -0.042 | 0.0% | 0.0% | 2.2% | 0.65 | 0.76 | 1306 |
| TOUCH_ONLY | 19 | 0.084 | 0.248 | 0.0% | 0.0% | 0.0% | 0.00 | 0.91 | — |
| Matched controls | 387 | 0.007 | 0.016 | 5.2% | 9.3% | 11.1% | 0.49 | 0.54 | 1198 |

### Same population — structural-stop R denominator

| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLOSE_BREAK | 126 | 0.029 | 0.175 | 17.5% | 26.2% | 24.6% | 1.13 | 1.53 | 1049 |
| WICK_REJECT | 95 | 0.000 | 0.034 | 16.8% | 14.7% | 20.0% | 0.96 | 1.18 | 232 |
| CLOSE_RECLAIM | 46 | -0.069 | -0.052 | 10.9% | 23.9% | 32.6% | 0.89 | 1.08 | 1058 |
| TOUCH_ONLY | 19 | 0.273 | 0.694 | 26.3% | 47.4% | 42.1% | 0.00 | 2.87 | — |
| Matched controls | 387 | 0.000 | 0.000 | 0.8% | 0.8% | 1.0% | 0.01 | 0.01 | 1059 |

### Holdout CLOSE_BREAK (4h invalidation)

| Event class | Events | Median fwd 15m | Median fwd 60m | 1R outcome-dir 60m | 2R session | 3R two-session | Median MAE | Median MFE | Time to 1R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLOSE_BREAK holdout ATR | 47 | 0.019 | 0.122 | 0.0% | 0.0% | 0.0% | 0.36 | 0.64 | 1315 |
| CLOSE_BREAK holdout structR | 47 | 0.062 | 0.245 | 19.1% | 23.4% | 31.9% | 0.81 | 1.59 | 1051 |

## Executive answers (dev, descriptive)

- CLOSE_BREAK 1R/60m (ATR) **0.0%** (n=126) vs controls **5.2%** (n=387); structR **17.5%**.
- WICK_REJECT 1R/60m (**reject / opposite** dir, ATR) **0.0%** (n=95); fail **33.7%**; structR **16.8%**.
- CLOSE_RECLAIM 1R/60m (reclaim dir, ATR) **0.0%** (n=46).
- Stance: **RESEARCH** — Phase 5 gated on `OUTCOME_DIRECTION_AND_R_UNIT_AUDIT.md` PASS + holdout + cross-market approval.
