# SPEC — GBPUSD Monday OR `M1_S1_R2`

**Status:** Phase 2 extended · **paper-only** (sub-period FAIL).  
**Plugin:** `monday_or_breakout` · `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Monday OR → Tue–Fri 15m close breakout → main 3 lots with DD ladder (2@30%, 1@50%) → shifted primary at opposite Mon extreme after flat@50% with **matched** 3-lot structure → HTF both-opposed skip → max **3** primary entries/week.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30%, 1@50% |
| `S1` | Shifted 3 = same as main |
| `R2` | Max **3** primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$231k |
| Stress DD | −$87k |
| **Net/Stress** | **2.67** |
| Baseline `M1_S1_R1` | 1.87 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **FAIL** (1/3) — same pattern as EURUSD: pre-2020 carries the book |
| Clustering | FLAG — top week ~18% of lifetime \|net\| |
| DD sensitivity | **PASS** — 25/45 N/S 2.45; 35/55 N/S 2.76 |

## Capacity sketch

Reserve **2–3M** notional for paper; do not fund live until ≥2/3 positive sub-period slices.

## Do-not-cross-use

Do not use USDJPY `M2_S3_*` or EURUSD light-sidecar sizing on GBPUSD without a fresh sweep.
