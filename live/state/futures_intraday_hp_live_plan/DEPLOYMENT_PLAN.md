# Futures HP deployment plan (`futures_intraday_hp_sizeup_v1`)

Hub: `live/state/futures_intraday_hp_live_plan/`  
Nulls 1.25×: `../futures_intraday_hp_sizeup_nulls/`  
Nulls 2×: `../futures_intraday_hp_sizeup_nulls_2x/`  
Compare: `COMPARISON.md` · `size_sensitivity.csv`

**Canonical objective:** whole-book **ΔN/S** (higher better). Δnet is
viability/reporting only. See `canonical_ns_research/POLICY.md`.

**Core result (2026-08-13 ΔN/S Phase-3 repair):** under the ΔN/S null
objective, **no** futures prior-opposed pair is **SIZE-UP VALIDATED** at
1.25×. ES ST-age and YM overnight-middle — previously Tier A on a Δnet-era
read — are **NOT VALIDATED** (`p_master_ΔNS` ≈ 0.77 / 0.99). Sole 1.25×
survivor: **NQ prior-opposed OR-norm** = **PROVISIONAL PAPER**. Highest
economic conviction remains **NQ OR-norm @ exact 2×** (also provisional;
see 2× hub).

Only **exact** stated multipliers have null-suite standing. Do **not**
infer 1.5×/2×/3×/4× from a 1.25× pass — `COMPARISON.md` columns are
sensitivity only.

---

## Deployment tiers

### Tier A — paper 1.25×

_None — no SIZE-UP VALIDATED survivors under ΔN/S._

| Book | Condition | Decision (ΔN/S) |
|---|---|---|
| ES prior-opposed legacy | ST-event age >180m (`st_age_gt180m`) | **NOT VALIDATED** (`p_master_ΔNS`≈0.77) |
| YM prior-opposed RL | Overnight middle third (`on_middle`) | **NOT VALIDATED** (`p_master_ΔNS`≈0.99) |

### Tier B — provisional paper 1.25×

| Book | Condition | Decision |
|---|---|---|
| NQ prior-opposed RL | Normal opening 15m range (`or_norm`) | PROVISIONAL PAPER (`p_master_ΔNS`≈0.074; ΔN/S +4.70) |

### Highest-conviction controlled paper (exact 2×, separate hub)

| Book | Condition | Decision |
|---|---|---|
| NQ prior-opposed RL | Normal opening 15m range (`or_norm`) | PROVISIONAL PAPER @ **2.00×** (`p_master_ΔNS`≈0.064; ΔN/S **+12.20**) |

ES/YM @2×: **NOT VALIDATED**. Operational stance for NQ @2×:
**HIGH-PRIORITY CONTROLLED PAPER** — not funded production.

### Tier C — shadow profile only

Historical shortlist RISK-BUDGET / RISK THROTTLE rows (no size change).
Re-score under ΔN/S before any promotion claim.

| Book | Condition | Notes |
|---|---|---|
| ES ST+PMC MA-bull | ST-event age >180m | RISK THROTTLE on shortlist ΔN/S rerun |
| NQ ST+PMC 3R | Entry hour (NY) = 11 | prior RISK-BUDGET PROFILE |
| NQ v2b S_1_1_3 | Prior RTH close mid-third | prior RISK-BUDGET PROFILE |
| YM prior-opposed RL | Prior RTH range normal | prior RISK-BUDGET PROFILE |
| YM ST+PMC 3R | Thursday | prior RISK-BUDGET PROFILE |

### No action

All **NOT VALIDATED** conditions — do not size, do not shadow-promote.

---

## Bookkeeping (Tier B / 2× provisional)

Retain **1.0× baseline** tracking and separately book the **incremental**
sleeve (0.25× at 1.25× stated, or +1.0× at exact 2×).

Per HP campaign / session row:

| Field | Notes |
|---|---|
| campaign date | session / entry date |
| HP flag | condition true before entry |
| condition inputs | causal feature values used |
| baseline intended size | 1.0× |
| incremental intended size | +0.25× or +1.0× as authorized |
| actual fills | broker fills at intended sizes |
| incremental realized P&L | incremental sleeve only |
| incremental stress / MAE | sleeve path |
| whole-book stress and drawdown | baseline + incremental combined |
| parity mismatch reason | if intended ≠ filled |

**Do not stack yet** — no simultaneous multi-book HP boosts; no micro+full
contract stacking on the same index sleeve.

---

## Prior-opposed overlap gate (required before any simultaneous HP)

Three prior-opposed candidates were studied (ES / YM / NQ). With ES/YM
demoted under ΔN/S, simultaneous prior-opposed HP is not currently in
scope. If ES/YM are ever re-validated, re-run:

```bash
python -m live.futures_intraday_hp_sizeup_compare --email
```

**Until any joint gate is explicitly cleared for simultaneous boosts,
implement: at most one prior-opposed HP multiplier across ES/YM/NQ per session.**

Current research-tape read: gate = `HOLD_ONE_HP_PER_SESSION`.

---

## Portfolio / sleeve rules

- One HP multiplier per economic index sleeve per session (no NQ+MNQ / YM+MYM / ES+MES).  
- No same-regime ST+PMC stacking without a separate overlap pass.  
- Tier C stays shadow-annotation only (no order-size change).  
- Tier B / 2× provisional: shadow first if lot geometry cannot express the
  multiplier cleanly; then controlled paper with incremental sleeve ledger.

---

## Repeatable drivers

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"

# Full study: select → profile → 1.25× nulls → LIVE_PLAN
python -m live.futures_intraday_hp_sizeup_v1 --email

# Phase-3 prior-opposed pairs @ 1.25× (ΔN/S)
python -m live.futures_intraday_hp_sizeup_nulls --phase3 --email

# Predeclared Tier A/B pairs @ exact 2× (separate hub)
python -m live.futures_intraday_hp_sizeup_nulls --predeclared-2x --email

# Baseline vs 1.25/2/3/4× + prior-opposed overlap
python -m live.futures_intraday_hp_sizeup_compare --email
```

Skill: `potions-futures-intraday-hp-sizeup`.
