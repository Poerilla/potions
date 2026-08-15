# OR Profile — research plans (2026-08-02)

Status: **Plan A executed & rejected**; **Plan B executed — time≤12:00 promoted**;
**Plan C steps 1–4 executed (2026H2fx)** — policy derive (step 5) deferred pending review.

Three planned follow-ups from the OR Profile Probability Engine work
(`live/or_profile_engine.py`, tables at `live/state/or_profile_engine/<mkt>/2026H2/`).
Each plan is frozen here before execution; thresholds cite the stable cells
they derive from so no re-peeking is needed at execution time.

---

## Plan A — Runner ladder from the extension chain

**Hypothesis.** Holding the S_1_1_3 runner block (3 units) past 2R only pays
when the state's extension chain P(2R|1R) x P(3R|2R) clears a threshold.
Stable cells (touch, all-four-markets agreement): q1 P(2R|1R) 0.62 / with
gap-up-sm 0.65-0.67; q4 P(2R|1R) 0.35 and P(3R|2R) 0.30-0.32.

**Design (a priori):**

- Ladder map, knowable at 09:45: chain = P(2R|1R) x P(3R|2R) from the
  frozen 2026H2 tables for the session's (or_width_q, gap_bucket) cell,
  falling back to or_width_q-only when the pair cell is below min-N.
  - chain >= 0.30 (q1 gap-up class): keep full runner, extend runner target
    from TP2 to 3R (`tp2` stays, runner rides to 3R stop-managed).
  - 0.18 <= chain < 0.30: current behaviour (runner to TP2, stop at BE).
  - chain < 0.18 (q4 class): no runner — 1/1/0 block (already validated as
    P3; this plan refines it from binary to a 3-tier ladder).
- Mechanism: date-list splits per tier (as in `or_profile_v2b_join.py`
  `SIZING_TIERS`) plus one new tier `runner_3r` needing a small
  `runner_target_r_mult` config knob in `v2b_scaleout`.

**Steps:**

1. Add `runner_target_r_mult` config knob (default 2.0 = current TP2 path).
2. Extend `SIZING_TIERS` with `runner_3r`; map tiers from the frozen tables.
3. Fit-window sanity on the joined tape (expected uplift per tier), register
   DSR ledger row, then frozen-policy validation replay 2025-01 -> 2026-06
   vs S_1_1_3 and vs P3 (NQ + MNQ).
4. Promote only if net/stress beats P3 on the validation window.

---

## Plan B — Asymmetric reverse leg (`reverse_only_when` state map)

**Hypothesis.** `oco_then_reverse` reverses unconditionally; the cells say
the reverse leg's edge is concentrated: P(opposite break | failed break) =
0.86-0.93 on q1 mornings vs 0.46 on 10:30-12:00 failures (all four markets,
13-14 stable years). Suppressing the reverse leg outside its edge states
should cut reverse-leg losses with minimal upside loss.

**Design (a priori):**

- New `v2b_scaleout` config map `reverse_only_when` with keys checkable at
  reverse-arm time (all causal): `max_first_leg_exit_time` (default 12:00),
  `or_width_q_allow` (default ["q1","q2"]), evaluated against a per-session
  quartile fed via config (same trailing-250 definition as the engine).
- Reverse leg arms only when all configured conditions hold; first leg
  entirely unchanged.
- Variants: (i) time-only gate 12:00; (ii) time + q1/q2; (iii) q1-only
  (strictest, matches the 0.92 cell).

**Steps:**

1. Config plumbing + arm-time gate in `_maybe_arm_next_leg` (reverse arm path).
2. Diagnostic split of the existing S_1_1_3 tape: reverse-leg-only PnL by
   or_width_q x first-leg-exit-time bucket (fit window <= 2024-12-31).
3. DSR ledger rows, frozen variants, validation replay 2025-01 -> 2026-06
   NQ + MNQ vs baseline and vs P5 combo (gate stacks orthogonally on P1/P3/P6).
4. Promote the best variant only if it improves net/stress AND reverse-leg
   PF on validation.

---

## Plan C — OR profile stats for the profitable Forex/CFD models

**Goal.** Re-derive the probability tables on the OANDA CFD markets backing
the live/demo books (US30, NAS100 first — both have profitable ST+PMC 1mfill
and v2b-family demos; then EURUSD/USDJPY/XAU for the Monday-OR/monthly-ORB
families) and check which stable futures cells carry over.

**Key differences to handle (design):**

1. **Sessions/clock:** US30/NAS100 CFDs track the same NY RTH — reuse the
   09:30-09:45 OR unchanged. FX pairs have no RTH; for EURUSD/USDJPY define
   the OR on the London open (03:00-03:15 NY) and NY open (08:00-08:15 NY)
   as two separate profile runs; XAU uses the NY-open variant.
2. **Data:** 1m OANDA mid candles already on disk for the demo markets
   (`fx/*_1m*.csv` / demo inherit paths); loader shim in the engine
   (`load_1m_by_ny_date_any` equivalent for OANDA CSVs, volume optional).
3. **Engine changes:** parametrize `OR_START`/`OR_END`/EOD per market config
   (currently constants); everything else (dual triggers, R-multiples,
   labels, Wilson/stability machinery) carries over untouched.
4. **Tables:** same TABLE_SPECS; add pip-based OR-width quartiles (points
   scale differs per pair, quartile logic is scale-free already).

**Steps:**

1. ~~Engine: market-config clock + OANDA loader (no logic changes).~~ Done
   (`live/fx_or_markets.py` + FX path in `or_profile_engine.run_market`).
2. ~~Run US30 + NAS100 (asof 2026H2fx); compare headline chains.~~ Done —
   chains ≈ NQ (see `2026H2fx_PLAN_C.md`).
3. ~~Run EURUSD/USDJPY + XAU.~~ Done (EURUSD London+NY, USDJPY NY, XAU NY).
4. Join to profitable model tapes:
   - ~~US30/NAS100 ST+PMC 1mfill~~ Done — **flat-gap/q4 do NOT transfer**
     (edges opposite NQ). Also joined EURUSD/USDJPY/XAU (relative ranks only;
     pip scaling not applied).
   - Monday-OR FX tapes — **still open**.
5. Policy derive + q1-fakeout satellite on US30/NAS100 — **deferred**.
   Futures satellite already BINNED; skip CFD satellite unless a new cell
   appears. Per-market FX policies must be re-fit (do not copy NQ P1/P3).

**Order of execution:** after the q1 fakeout satellite review (done — BINNED).
