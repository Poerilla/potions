# FX sleeve-overlap & joint-stress board

Not another leverage ladder — pairwise **active-date overlap**, direction
agreement, **joint reachable stress** (path DD of summed daily nets),
daily P&L correlation, and **maximum simultaneous margin**.

Margin proxy: EURUSD/GBPUSD/USDJPY = **$2,000 / unit** (same as $250k board).
EURUSD Thursday sleeve sized at **1.25×** (SIZE-UP VALIDATED).
Asia-range = unfiltered `S_3_1_3` (THREE_BOOK A); filtered Asia = `S_3_1_3_flt` (C).
Unfiltered↔filtered is a **nested SAME_SLEEVE** (flt ⊂ unfilt) — joint stress /
margin if both are stacked is a counterfactual warning, not a deployable book.

Driver: `python -m live.fx_sleeve_overlap_board --email`

## Board

| pair | shared dates | same-dir rate | joint stress | daily ρ | max simul. margin | regime |
|---|---:|---:|---:|---:|---:|---|
| USDJPY Asia-range ↔ USDJPY Monday OR | 413 | 81.6% | -$54,421 | +0.022 | +$22,000 | CONDITIONAL_OVERLAP |
| USDJPY Asia-range ↔ USDJPY filtered Asia | 770 | 100.0% | -$59,735 | +1.000 | +$28,000 | SAME_SLEEVE |
| USDJPY Monday OR ↔ GBPUSD fair 3R | 266 | 56.8% | -$20,940 | -0.075 | +$10,000 | SEPARATE_REGIMES |
| USDJPY Monday OR ↔ EURUSD ST+PMC Thursday | 46 | 50.0% | -$18,730 | -0.184 | +$10,500 | SEPARATE_REGIMES |
| EURUSD ST+PMC Thursday ↔ GBPUSD fair 3R | 42 | 88.1% | -$13,007 | +0.288 | +$4,500 | CONDITIONAL_OVERLAP |

### Ops appendix (demo filtered Asia)

| pair | shared dates | same-dir rate | joint stress | daily ρ | max simul. margin | regime |
|---|---:|---:|---:|---:|---:|---|
| USDJPY filtered Asia (demo) ↔ USDJPY Monday OR | 207 | 82.6% | -$26,216 | -0.130 | +$22,000 | CONDITIONAL_OVERLAP |

## Detail

### USDJPY Asia-range ↔ USDJPY Monday OR

- **A:** USDJPY Asia-range unfiltered S_3_1_3 (n=1673, stress=-$68,164, max margin=+$14,000)
- **B:** USDJPY Monday OR M2_S3_R1 skip Aug/Sep (n=1907, stress=-$19,315, max margin=+$8,000)
- Shared active NY dates: **413** / union 2687 (Jaccard 0.154)
- Same-direction rate on shared dates: **81.6%** (345 same-day same-dir events)
- Daily P&L corr (shared days): **+0.022** (n=413); union corr +0.007
- Joint reachable stress (union daily path): **-$54,421** · shared-day path -$27,835 · additive UB -$87,479
- Joint net / N/S: +$448,293 / 8.24
- Max simultaneous margin: **+$22,000**
- Regime class: **CONDITIONAL_OVERLAP** — strategies can exist separately; apply a simultaneous-signal shared risk cap when both fire

### USDJPY Asia-range ↔ USDJPY filtered Asia

- **A:** USDJPY Asia-range unfiltered S_3_1_3 (n=1673, stress=-$68,164, max margin=+$14,000)
- **B:** USDJPY filtered Asia S_3_1_3_flt (n=861, stress=-$20,640, max margin=+$14,000)
- Shared active NY dates: **770** / union 1484 (Jaccard 0.519)
- Same-direction rate on shared dates: **100.0%** (861 same-day same-dir events)
- Daily P&L corr (shared days): **+1.000** (n=770); union corr +0.839
- Joint reachable stress (union daily path): **-$59,735** · shared-day path -$41,279 · additive UB -$88,803
- Joint net / N/S: +$332,770 / 5.57
- Max simultaneous margin: **+$28,000**
- Regime class: **SAME_SLEEVE** — one shared allocation; do not count as independent edges or stack full risk
- **Nested filter:** filtered ⊂ unfiltered; do not sum nets/margin as independent risk — pick one Asia book.

### USDJPY Monday OR ↔ GBPUSD fair 3R

- **A:** USDJPY Monday OR M2_S3_R1 skip Aug/Sep (n=1907, stress=-$19,315, max margin=+$8,000)
- **B:** GBPUSD fair 3R (sl50/tp150) (n=1026, stress=-$12,295, max margin=+$2,000)
- Shared active NY dates: **266** / union 2361 (Jaccard 0.113)
- Same-direction rate on shared dates: **56.8%** (151 same-day same-dir events)
- Daily P&L corr (shared days): **-0.075** (n=266); union corr -0.019
- Joint reachable stress (union daily path): **-$20,940** · shared-day path -$14,894 · additive UB -$31,610
- Joint net / N/S: +$403,563 / 19.27
- Max simultaneous margin: **+$10,000**
- Regime class: **SEPARATE_REGIMES** — independent strategy allocations; still subject to underlying-market and portfolio stress caps

### USDJPY Monday OR ↔ EURUSD ST+PMC Thursday

- **A:** USDJPY Monday OR M2_S3_R1 skip Aug/Sep (n=1907, stress=-$19,315, max margin=+$8,000)
- **B:** EURUSD ST+PMC Thursday @1.25× (n=175, stress=-$5,081, max margin=+$2,500)
- Shared active NY dates: **46** / union 1744 (Jaccard 0.026)
- Same-direction rate on shared dates: **50.0%** (23 same-day same-dir events)
- Daily P&L corr (shared days): **-0.184** (n=46); union corr -0.023
- Joint reachable stress (union daily path): **-$18,730** · shared-day path -$8,301 · additive UB -$24,396
- Joint net / N/S: +$337,737 / 18.03
- Max simultaneous margin: **+$10,500**
- Regime class: **SEPARATE_REGIMES** — independent strategy allocations; still subject to underlying-market and portfolio stress caps

### EURUSD ST+PMC Thursday ↔ GBPUSD fair 3R

- **A:** EURUSD ST+PMC Thursday @1.25× (n=175, stress=-$5,081, max margin=+$2,500)
- **B:** GBPUSD fair 3R (sl50/tp150) (n=1026, stress=-$12,295, max margin=+$2,000)
- Shared active NY dates: **42** / union 1143 (Jaccard 0.037)
- Same-direction rate on shared dates: **88.1%** (37 same-day same-dir events)
- Daily P&L corr (shared days): **+0.288** (n=42); union corr +0.029
- Joint reachable stress (union daily path): **-$13,007** · shared-day path -$6,160 · additive UB -$17,376
- Joint net / N/S: +$153,368 / 11.79
- Max simultaneous margin: **+$4,500**
- Regime class: **CONDITIONAL_OVERLAP** — strategies can exist separately; apply a simultaneous-signal shared risk cap when both fire

### USDJPY filtered Asia (demo) ↔ USDJPY Monday OR

- **A:** USDJPY filtered Asia S_3_1_3_flt (n=861, stress=-$20,640, max margin=+$14,000)
- **B:** USDJPY Monday OR M2_S3_R1 skip Aug/Sep (n=1907, stress=-$19,315, max margin=+$8,000)
- Shared active NY dates: **207** / union 2179 (Jaccard 0.095)
- Same-direction rate on shared dates: **82.6%** (175 same-day same-dir events)
- Daily P&L corr (shared days): **-0.130** (n=207); union corr -0.030
- Joint reachable stress (union daily path): **-$26,216** · shared-day path -$21,977 · additive UB -$39,955
- Joint net / N/S: +$472,410 / 18.02
- Max simultaneous margin: **+$22,000**
- Regime class: **CONDITIONAL_OVERLAP** — strategies can exist separately; apply a simultaneous-signal shared risk cap when both fire

## Read guide

- **SEPARATE_REGIMES** — low calendar overlap and weak shared-day linkage; still
  respect portfolio stress / margin caps.
- **CONDITIONAL_OVERLAP** — sparse co-firing but high same-dir or ρ when both
  active → apply a simultaneous-signal shared risk cap.
- **SAME_SLEEVE** — meaningful overlap + high conditional linkage → one
  allocation, do not stack full independent risk.
