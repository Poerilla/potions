# Causality of chart levels (HP liq-run / band overlays)

## Always both band directions

Rolling **up** and **down** extension bands are computed every month from the
same prior-month path stats. There is no live condition that “creates” only one
side — both sides exist whenever the 6-month rolling window is available.

What *does* choose a **trade direction** for the fade book is the **liquidity
run** (largest |extension| from month open in the first N NY days).

## When each object is known

| Object | Known at | Causal rule |
|---|---|---|
| Up/dn min, med, max (**ATR multiples**) | **Before month open** | Mean of prior months only (`(y,m) < current`); 6-month roll |
| Month open | First bar of month | Session open |
| Band **prices** (`open ± atr×mult`) | Month open | Needs open + prior ATR from completed prior month |
| Liq side, `p_liq`, ext | **`t_liq`** | Extreme must print in first N NY days |
| 1R stop (= `p_liq ± ext`) | **`t_liq`** | Same |
| Envelope range (all horizontals incl. SL) | **`t_liq`** | Max/min of open, both bands, `p_liq`, 1R stop |

## Variant A — band-max fade

- Direction from liq run (fade).
- Entry limit at **dn max** (long) / **up max** (short).
- Target = month open.
- Stop distance = **liq-run size** (same R as base book, measured from band-max entry).
- Arm only after `t_liq` (same as base). Re-entry policy unchanged (TP re-arms; stop waits open touch).

## Variant B — range breakout sidecar

- Wait until `t_liq` (full range causal).
- **No breakout signal during the liq-run window** (`ts < arm_after_ts`).
- Signal: **4h close** outside `[range_low, range_high]`.
- Then arm **limit** at the broken boundary (follow-through).
- SL = **2 × liq-run size**; target = **range size**.
- Max **2** attempts; after a stop, re-arm only after another 4h close outside + limit at boundary.
- If 2×liq SL is too tight, swap to SL = range size (sensitivity later).
- Persistent fails → research fade-outside-range later (not in this pass).
