# Plan C — FX/CFD OR profile (asof 2026H2fx)

Status: **tables + index ST+PMC join done**; policy derive deferred (step 5).

## Headline chains (touch, condition=all)

| Market | P(1R\|break) | P(2R\|1R) | P(reentry\|break) | P(opp break\|fail) | P(opp 1R\|opp break) |
|--------|-------------:|----------:|------------------:|-------------------:|---------------------:|
| NQ futures (2026H2) | 0.542 | 0.497 | 0.893 | 0.778 | 0.165 |
| US30 CFD | 0.558 | 0.485 | 0.907 | 0.735 | 0.154 |
| NAS100 CFD | 0.547 | 0.502 | 0.888 | 0.758 | 0.159 |
| EURUSD London OR | 0.867 | 0.839 | 0.974 | 0.990 | 0.195 |
| EURUSD NY OR | 0.769 | 0.747 | 0.948 | 0.969 | 0.253 |
| USDJPY NY OR | 0.777 | 0.757 | 0.950 | 0.963 | 0.221 |
| XAU NY OR | 0.801 | 0.785 | 0.964 | 0.976 | 0.211 |

**Carry-over (chains):** US30/NAS100 match NQ within ~2–4 pts on the five headline cells — index CFD microstructure of the OR game looks futures-like.

**FX pairs/XAU:** much higher continuation rates (narrower OR vs session?). Do **not** reuse NQ cell thresholds without re-fitting.

## ST+PMC 1mfill join

Hub: [`fx_join/2026H2fx/SUMMARY.md`](fx_join/2026H2fx/SUMMARY.md).

**US30 / NAS100 (index points — meaningful scale):**
- Flat-gap and q4 edges are **positive** vs all on both CFDs — **opposite** of NQ P1/P3.
- **Do not import** flat-gap skip or q4 no-runner onto US30/NAS100 ST+PMC from futures overlays.
- Large-gap days (esp. gap_up_lg / gap_dn_lg on NAS100) are the relative drags.

**EURUSD / USDJPY / XAU:** joined for relative cell ranking only (priceΔ without pip/$ multipliers → near-zero absolute means on FX). Flat still tends to rank best; large up-gaps worst — same qualitative pattern as index CFDs, opposite NQ overlays.

## Companion: FX turtle soup

Hub: [`../../fx_turtle_soup/SUMMARY.md`](../../fx_turtle_soup/SUMMARY.md).

Index CFD OR soup dead; only EURUSD London OR+wick25 green (+$20k PF 1.25, 9/24 neg yrs) — research lead, not promote.

## Artifacts

- Clocks/loader: `live/fx_or_markets.py`
- Engine: `live/or_profile_engine.py` (FX-aware `run_market`)
- Join: `live/fx_or_profile_join.py`
- Tables: `live/state/or_profile_engine/<mkt>/2026H2fx/`

## Next (after review)

1. Per-market policy fit on FX clocks (not copy NQ P1/P3).
2. Monday-OR join for EURUSD/USDJPY weekly family.
3. Skip q1-fakeout satellite on US30/NAS100 (futures satellite already BINNED).
