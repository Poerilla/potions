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

# Standalone compare (baseline vs 1.25/2/3/4× + prior-opposed overlap)
python -m live.futures_intraday_hp_sizeup_compare --email
```

Drivers:

- `live/futures_intraday_hp_sizeup_v1.py` — orchestrator
- `live/futures_intraday_condition_profile.py` — features + shortlist
- `live/futures_intraday_hp_sizeup_nulls.py` — placebo / shift / master / WF
- `live/futures_intraday_hp_sizeup_compare.py` — sensitivity + overlap
- `live/futures_intraday_hp_sizeup_lib.py` — catalog / COND_COL / hubs

## Decision labels (1.25× only)

| Label | Meaning |
|-------|---------|
| SIZE-UP VALIDATED | All gates; Tier A paper |
| PROVISIONAL PAPER | Same except `0.05 < p_master ≤ 0.10`; Tier B controlled paper |
| RISK-BUDGET PROFILE | Timing interesting but master/WF fail; Tier C shadow only |
| NOT VALIDATED | No action |

Do **not** promote 2×/3×/4× from a 1.25× pass. Rerun the full null suite at the
intended multiplier.

## Deployment tiers (canonical)

See [`DEPLOYMENT_PLAN.md`](../../../live/state/futures_intraday_hp_live_plan/DEPLOYMENT_PLAN.md)
(also `LIVE_PLAN.md`, `hp_size_rules.yaml`).

| Tier | Action | Candidates |
|------|--------|------------|
| **A** | paper 1.25× | ES prior-opposed ST-age>180m; YM prior-opposed overnight middle |
| **B** | provisional paper 1.25× | NQ prior-opposed normal OR |
| **C** | shadow profile only | NQ ST+PMC h11; NQ v2b prior-RTH mid; YM prior-RTH-norm; YM ST+PMC Thu |
| — | no action | all NOT VALIDATED |

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

1. Open `DEPLOYMENT_PLAN.md` + `COMPARISON.md` + nulls `SUMMARY.md`.
2. Lead with Tier A validated survivors and 1.25× vs baseline (net / MTM DD / N/S / yearly).
3. Note Tier B provisional and Tier C shadow-only; call out 2–4× as sensitivity only.
4. Cite overlap hold-one-HP rule and bookkeeping fields.
5. Stance: two causal-looking 1.25× allocations survived full nulls — not a long untrustworthy bucket list.
6. After material runs: `potions-tracker-docs` (tracker / CHANGE_LOG / PROGRESS).

## Related

- `potions-job-email` — always notify on complete/crash
- `potions-intraday-condition-profile` — FX/index CFD profile cousin
- `potions-tracker-docs` — tracker / CHANGE_LOG / PROGRESS after material runs
- `potions-repo-router` — task routing
