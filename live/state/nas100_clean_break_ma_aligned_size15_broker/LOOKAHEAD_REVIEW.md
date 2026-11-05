# LOOKAHEAD_REVIEW — NAS100 clean-break ma_aligned size_1.5

**Date:** 2026-09-13
**Status:** CONDITIONAL_PASS
**Parent result DSR:** `TRL-2026-00199`  **Audit DSR:** `TRL-2026-00200`
**Hub:** `/home/tester/hsm/potions/live/state/nas100_clean_break_ma_aligned_size15_broker`

## Scope

Frozen OANDA NAS100 `trail06_m4_e2_out_be` 1m-fill Engine tape + HA overlay
`5m MA vs trade = ma_aligned | size_1.5` (research size-up on HP campaigns).

## 1) Engine order-time causality — PASS

| Check | Value |
|---|---:|
| Feature snapshots | 22558 |
| Causality violation rows | 0 |
| Feature order fails (`event≤available≤bar`) | 0 |
| Non-MOC fills at/before `live_after_ts` | 0 |
| Entry fills at/before arm | 0 |

Source: `live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/states/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill`

## 2) `ma5_align` feature recipe — PASS

Recipe (shared HA mill): 5m SMA9/SMA21 on completed bars; availability
stamped at left-label **+5m**; `merge_asof(..., direction=backward)` on
entry fill `entry_ts`. Marked `live_ready` in `intraday_condition_overlay.CAUSAL_LIVE_READY`.

| Check | Value |
|---|---:|
| Campaigns | 1166 |
| Stored vs independent fill-asof mismatch | 0 |
| Feature `available_at` **after** entry (lookahead) | 0 |
| Feature `available_at` **equal** entry (just-completed 5m) | 515 |

## 3) Stop-arm vs fill MA (size-up contract) — CONDITIONAL

Entry is a **resting buy/sell stop** armed at OR finalize (`live_after_ts`),
then filled later on the 1m tape (median arm→fill delay ~4m; max hours).
Fill-asof `ma_aligned` uses bars that can complete **after arm**. That is
**not** lookahead vs the fill instant, but it **is** information the resting
order did not have at submit unless live **refreshes qty** from the latest
completed 5m MA until fill.

| Metric | Fill-asof (research) | Arm-asof (no refresh) |
|---|---:|---:|
| HP campaigns | 710 (61%) | 647 |
| Label flips arm↔fill | — | 135 |
| HP only at fill (not arm) | 99 | — |
| HP only at arm (not fill) | — | 36 |
| Campaign Δnet @ ×1.5 | $+6195 | $+4754 |

### Engine+PaperBroker weighted stress (same unit tape)

| Book | Net | Stress | N/S | Δnet | ΔN/S |
|---|---:|---:|---:|---:|---:|
| Baseline (×1) | $12253 | $1966 | 6.23 | — | — |
| Fill-asof HP ×1.5 | $18448 | $2466 | 7.48 | $+6195 | +1.25 |
| Arm-asof HP ×1.5 | $17007 | $2498 | 6.81 | $+4754 | +0.58 |

Flip detail: `live/state/nas100_clean_break_ma_aligned_size15_broker/causality_audit/ma_arm_fill_flips.csv`

## Verdict

- **No Engine lookahead** on the frozen 1m-fill tape (`live_after_ts` +
  feature snapshots clean).
- **`ma5_align` itself is point-in-time at fill** (completed 5m only).
- **Research size_1.5 lift assumes fill-asof HP.** Under a stricter
  arm-only size contract the Engine lift shrinks but remains positive
  (Δnet $+6195 → $+4754; ΔN/S +1.25 → +0.58).
- **Stance unchanged: RESEARCH.** Promote only after wiring live qty
  refresh from completed 5m MA (match fill-asof) **or** restating the
  book on arm-asof HP.

## Residual risks (not auto-fail)

- Synthetic 1m bid/ask on the parent 1m-fill validation (not true quotes).
- 515 / 1166 fills use a 5m bar with `available_at == entry_ts` (bar that
  just completed at the fill left-label) — consistent with 1m processing
  after the prior minute closes.
- Demo plugin does not yet implement ma_aligned size-up.

DSR audit: `TRL-2026-00200` (parent `TRL-2026-00199`)
