---
name: potions-futures-intraday-hp-sizeup
description: >-
  Runs the futures intraday HP size-up study (top-book select, condition
  profile, 1.25× matched-added-exposure nulls, portfolio overlap, LIVE_PLAN
  tiers A/B/C, and baseline vs 2–4× sensitivity). Use for ES/YM/NQ prior-opposed
  or ST+PMC conditional size-up, futures HP validation, deployment plan, or
  prior-opposed overlap gates.
---

# Futures intraday HP size-up (`futures_intraday_hp_sizeup_v1`)

Hubs:

| Hub | Role |
|-----|------|
| [`live/state/futures_intraday_condition_profile/`](../../../live/state/futures_intraday_condition_profile/) | Campaign tapes + shortlist |
| [`live/state/futures_intraday_hp_sizeup_nulls/`](../../../live/state/futures_intraday_hp_sizeup_nulls/) | 1.25× null suite + decisions |
| [`live/state/futures_intraday_hp_sizeup_nulls_2x/`](../../../live/state/futures_intraday_hp_sizeup_nulls_2x/) | Predeclared Tier A/B @ exact 2× (separate) |
| [`live/state/futures_intraday_hp_live_plan/`](../../../live/state/futures_intraday_hp_live_plan/) | LIVE_PLAN / DEPLOYMENT_PLAN / compare |

## Environment

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
```

## Repeatable runs

Always pass `--email` (skill `potions-job-email`).

```bash
# Full pipeline: select top-8 → profile → 1.25× nulls → LIVE_PLAN → compare
python -m live.futures_intraday_hp_sizeup_v1 --email

# Smoke (reduced null counts, max 2 pairs)
python -m live.futures_intraday_hp_sizeup_v1 --email --smoke

# Profile only / nulls only
python -m live.futures_intraday_hp_sizeup_v1 --email --profile-only
python -m live.futures_intraday_hp_sizeup_v1 --email --nulls-only

# Predeclared Tier A/B @ exact 2× (separate hub; does not rewrite 1.25× LIVE_PLAN)
python -m live.futures_intraday_hp_sizeup_nulls --predeclared-2x --email

# Standalone compare (baseline vs 1.25/2/3/4× + prior-opposed overlap)
python -m live.futures_intraday_hp_sizeup_compare --email

# NQ OR-norm only: linear 5×/10× + entry-bar liquidity (sensitivity, not nulls)
python -m live.futures_intraday_hp_nq_or_norm_extreme_size --email

# Add-on: NAS100 NQ-lead prior-opposed (dedicated hub; does not rewrite LIVE_PLAN)
python -m live.futures_intraday_hp_sizeup_nas100_nq_lead --email
```

Drivers:

- `live/futures_intraday_hp_sizeup_v1.py` — orchestrator
- `live/futures_intraday_condition_profile.py` — features + shortlist
- `live/futures_intraday_hp_sizeup_nulls.py` — placebo / shift / master / WF
- `live/futures_intraday_hp_sizeup_compare.py` — sensitivity + overlap
- `live/futures_intraday_hp_sizeup_lib.py` — catalog / COND_COL / hubs

## Decision labels (ΔN/S objective)

| Label | Meaning |
|-------|---------|
| SIZE-UP VALIDATED | All gates on **ΔN/S**; Tier A paper |
| PROVISIONAL PAPER | Same except `0.05 < p_master_ΔNS ≤ 0.10`; Tier B controlled paper |
| RISK THROTTLE | Timing interesting but master/WF fail; Tier C shadow only |
| NOT VALIDATED | No action |

Canonical score: whole-book **ΔN/S** (higher better). Δnet is report-only.
See [`canonical_ns_research/POLICY.md`](../../../live/state/canonical_ns_research/POLICY.md).

Do **not** promote 2×/3×/4× from a 1.25× pass. Rerun the full null suite at the
intended multiplier (`--predeclared-2x` for Tier A/B @ exact 2× into
`futures_intraday_hp_sizeup_nulls_2x/`).

**NQ OR-norm @2×** is the highest-conviction HP size-up in current research
(N/S 24.06→36.26, ΔN/S +12.20) but remains **PROVISIONAL / HIGH-PRIORITY
CONTROLLED PAPER** (selection-aware master borderline) — not funded production.

Under the 2026-08-13 ΔN/S Phase-3 repair, **ES ST-age** and **YM overnight-middle**
are **NOT VALIDATED** at 1.25× and 2× (`p_master_ΔNS` ≈ 0.77 / 0.99 @1.25×).
Tier A is empty; sole 1.25× survivor is NQ OR-norm **PROVISIONAL PAPER**.

## Deployment tiers (canonical)

See [`DEPLOYMENT_PLAN.md`](../../../live/state/futures_intraday_hp_live_plan/DEPLOYMENT_PLAN.md)
(also `LIVE_PLAN.md`, `hp_size_rules.yaml`).

| Tier | Action | Candidates |
|------|--------|------------|
| **A** | paper 1.25× | _none_ (ES/YM demoted under ΔN/S) |
| **B** | provisional paper 1.25× | NQ prior-opposed normal OR |
| **2×** | controlled paper (separate hub) | NQ OR-norm @ exact 2× (highest conviction) |
| **C** | shadow profile only | ES ST+PMC ST-age; NQ ST+PMC h11; NQ v2b prior-RTH mid; YM prior-RTH-norm; YM ST+PMC Thu |
| — | no action | all NOT VALIDATED (incl. ES/YM prior-opposed) |

### Tier A/B bookkeeping (do not stack yet)

Retain **1.0× baseline** tracking and separately book the **incremental 0.25×**:

- campaign date, HP flag, condition inputs
- baseline intended size, incremental intended size, actual fills
- incremental realized P&L, incremental stress / MAE
- whole-book stress and drawdown
- reason for any parity mismatch

### Prior-opposed overlap gate

Three prior-opposed candidates (ES / YM / NQ). Before any **simultaneous** HP
multiplier, re-run compare → `prior_opposed_overlap_report.csv` and report:

shared HP dates · same-direction rate · incremental P&L correlation ·
incremental joint stress · worst simultaneous loss · margin at simultaneous
boosted positions.

Until cleared: **at most one prior-opposed HP multiplier across ES/YM/NQ per session.**

## Report order

1. Open `DEPLOYMENT_PLAN.md` + `COMPARISON.md` + nulls `SUMMARY.md` (+ 2× hub).
2. Lead with ΔN/S labels: Tier A empty; NQ OR-norm provisional @1.25× and @2×.
3. Note ES/YM demotion under ΔN/S; Tier C shadow-only; 3–4× sensitivity only.
4. Cite overlap hold-one-HP rule and bookkeeping fields.
5. Stance: highest conviction = NQ OR-norm @2× controlled paper — not funded production.
6. Full unsorted coupon dump: [`canonical_ns_research/ALL_RESULTS.md`](../../../live/state/canonical_ns_research/ALL_RESULTS.md).
7. After material runs: `potions-tracker-docs` (tracker / CHANGE_LOG / PROGRESS).

## Related

- `potions-job-email` — always notify on complete/crash
- `potions-intraday-condition-profile` — FX/index CFD profile cousin
- `potions-tracker-docs` — tracker / CHANGE_LOG / PROGRESS after material runs
- `potions-repo-router` — task routing
- `python -m live.canonical_ns_research --email` — ledger / boards refresh
- `python -m live.canonical_ns_portfolio --email` — Phase-4 portfolio N/S under HOLD_ONE
