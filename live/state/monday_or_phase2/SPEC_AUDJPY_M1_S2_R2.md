# SPEC — AUDJPY Monday OR `M1_S2_R2`

**Status:** Phase 2 extended · sub-periods **PASS** (3/3).  
**Plugin:** `monday_or_breakout` · same light-sidecar recipe as EURUSD.

## Logic (plain English)

Same Monday OR + shifted-primary framework. Sizing matches EURUSD: main 3=(2@30,1@50), shifted 2=(1@30,1@50), max 3 primary/week, HTF both-opposed skip.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30%, 1@50% |
| `S2` | Shifted 2 = 1@30%, 1@50% |
| `R2` | Max **3** primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$96k |
| Stress DD | −$52k |
| **Net/Stress** | **1.83** |
| Baseline `M1_S1_R1` | 1.07 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 3/3 |
| Clustering | FLAG — top week ~20% of lifetime \|net\| (concentration review) |
| DD sensitivity | **PASS** — 25/45 N/S 1.59 (−13%); 35/55 N/S 2.32 |

## Capacity sketch

Initial **1–2M** notional equivalent (JPY cross; use ≈USD @ 110 for risk reporting). Smaller absolute edge than USDJPY — size below GBP/USDJPY.

## Do-not-cross-use

Shares EURUSD’s light-sidecar tag but **not** interchangeable with USDJPY `M2_S3_*`. Treat as a satellite sleeve, not a USDJPY substitute.

## Deployment

Eligible for limited paper / small live under EURUSD-like gates (N/S ≥ 1.5) **if** clustering FLAG is accepted and live DD stays in band. Prefer USDJPY as primary FX Monday OR book.
