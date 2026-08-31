# STRATEGY_PROTOTYPES — NQ structure-change Phase 5

**Updated:** 2026-08-30 09:20 ET
**Hub:** `live/state/nq_structure_change_phase5_prototypes/`
**Scope:** 4h invalidation, pen≥0.05 ATR only. No 1h mix. No runners/scale/filters.
**Execution:** 1m stop-first, gap-through stops, ±1 tick entry slippage, $1.50 fee, NQ $20/pt.
**Horizon:** hold until 1R stop/target or `two_session_end` (no same-day EOD cut).
**Causality:** `available_at < order_active_ts < fill_ts` — **0** violations on A (173) and B (122).
**Holdout:** locked read — no parameter changes after peek.

## Sample charts

Five 15m charts per event class under `sample_charts/` (+ `sample_charts.zip`).
Window ≈ confirm ± ~1 session; yellow = confirm 4h window; blue dashed = protected swing.

| Class | Charts |
|---|---:|
| CLOSE_BREAK | 5 |
| WICK_REJECT | 5 |
| CLOSE_RECLAIM | 5 |
| TOUCH_ONLY | 5 |

## Narrow question 1 — Prototype A (close-break continuation 1R/1R)

Does low structural-risk geometry have positive expectancy after costs + gap-through?

| Slice | n | net $ | avg $ | WR | PF | mean R | median R | gap-thru |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **dev (locked)** | 126 | **−9,969** | −79 | 54.8% | 0.74 | −1.45 | — | 12 |
| holdout | 47 | +26,074 | +555 | 51.1% | 1.56 | −4.31 | — | 4 |
| ALL | 173 | +16,106 | +93 | 53.8% | 1.19 | −2.23 | +0.19 | 16 |

Exit mix (ALL): target_1R 75 / stop 62 / horizon_end 36.
Stop exits include fat-tail gap-through (min R ≈ −125 on micro-stops); dollar PF can diverge from mean R when risk sizes vary.

**Answer:** **No on locked dev.** Base 1R/1R continuation fails dollar expectancy in-sample (−$79/trade, PF 0.74). Holdout dollar strength does **not** overturn a failed locked primary; mean R remains pathological from gap-through on tight stops.

**Stance A:** **REJECT** base 1R/1R continuation.

## Narrow question 2 — Prototype B (wick-reject fade 1R/1R)

Does confirmed structural rejection have simple executable reversal expectancy?

| Slice | n | net $ | avg $ | WR | PF | mean R | median R | gap-thru |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **dev (locked)** | 95 | **+2,178** | +23 | 40.0% | 1.05 | −0.21 | — | 1 |
| holdout | 27 | +15,090 | +559 | 51.9% | 1.47 | +0.08 | — | 0 |
| ALL | 122 | +17,267 | +142 | 42.6% | 1.22 | −0.15 | −0.34 | 1 |

Exit mix (ALL): stop 48 / target_1R 38 / horizon_end 36.
Horizon_end drag is material (−$18k ALL); wins are larger-$ when risk_pts are wide.

**Answer:** **Marginal / fragile.** Dev dollar expectancy is barely positive (+$23/trade, PF 1.05) with **negative** mean R. Holdout is better (n=27) but was not used for tuning — still too thin to call tradeable.

**Stance B:** **RESEARCH** — not reject on dollars, not promote. Needs a follow-on question (not target optimization): e.g. min stop distance / gap filter, or horizon policy — only after a predeclared contract.

## Narrow question 3 — Prototype C (reclaim invalidation of A)

Does exiting an open A trade at reclaim improve outcome vs holding to 1R/1R?

| Slice | reclaim exits used | Δnet vs A |
|---|---:|---:|
| dev | **0 / 126** | +0 |
| holdout | **0 / 47** | +0 |
| ALL | **0 / 173** | +0 |

Of 62 CLOSE_RECLAIM events whose parent CLOSE_BREAK is in A, **all 62** A trades had already hit stop or 1R target **before** reclaim `order_active_ts`. Under fast structural 1R/1R resolution, reclaim never becomes an actionable management exit.

**Answer:** **Not testable on this geometry.** Reclaim invalidation is vacuous when the base book resolves inside the first 4h window. C is not a separate alpha claim here.

**Stance C:** **N/A / deferred** until a slower management book (multi-R or time stop) leaves trades open into the reclaim window.

## Guardrails honored

- Not claiming 4h events beat controls on absolute ATR expansion.
- Structural-stop R vs matched controls not used as a trading claim.
- Targets fixed at 1R; no optimization; 4h only; holdout locked.
- Causality logging strict; 1m stop-first fills.

## Bottom line

Tight structural stops can print attractive **session structR hit rates** in the atlas, but the executable **1R/1R continuation (A) does not survive costs + gap-through on locked dev**. Wick-reject fade (B) is only marginally positive and R-unstable. Reclaim management (C) never fires on this base book.

Next narrow question (if continuing): predeclare a **minimum stop-distance / anti-micro-stop gate** or a **horizon policy** for B only — still no runners, no RSI/TOD filters, holdout still locked for the final read.
