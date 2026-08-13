# Futures HP deployment plan (`futures_intraday_hp_sizeup_v1`)

Hub: `live/state/futures_intraday_hp_live_plan/`  
Nulls: `../futures_intraday_hp_sizeup_nulls/`  
Compare: `COMPARISON.md` · `size_sensitivity.csv`

**Core result:** the futures study found **two** distinct, causal-looking
**1.25×** conditional allocations that survived the full null framework
(ES ST-age>180m, YM overnight-middle), rather than a large list of attractive
but untrustworthy historical buckets. NQ prior-opposed OR-norm is provisional.

Only **exact 1.25×** is authorized where noted. Do **not** infer 1.5×/2×/3×/4×
from a 1.25× pass — those columns in `COMPARISON.md` are sensitivity only.

---

## Deployment tiers

### Tier A — paper 1.25×

| Book | Condition | Decision |
|---|---|---|
| ES prior-opposed legacy | ST-event age >180m (`st_age_gt180m`) | SIZE-UP VALIDATED |
| YM prior-opposed RL | Overnight middle third (`on_middle`) | SIZE-UP VALIDATED |

### Tier B — provisional paper 1.25×

| Book | Condition | Decision |
|---|---|---|
| NQ prior-opposed RL | Normal opening 15m range (`or_norm`) | PROVISIONAL PAPER |

### Tier C — shadow profile only

| Book | Condition | Decision |
|---|---|---|
| NQ ST+PMC 3R | Entry hour (NY) = 11 | RISK-BUDGET PROFILE |
| NQ v2b S_1_1_3 | Prior RTH close mid-third | RISK-BUDGET PROFILE |
| YM prior-opposed RL | Prior RTH range normal | RISK-BUDGET PROFILE |
| YM ST+PMC 3R | Thursday | RISK-BUDGET PROFILE |

### No action

All **NOT VALIDATED** conditions — do not size, do not shadow-promote.

---

## Bookkeeping (Tier A / B)

Retain **1.0× baseline** tracking and separately book the **incremental 0.25×** P&L.

Per HP campaign / session row:

| Field | Notes |
|---|---|
| campaign date | session / entry date |
| HP flag | condition true before entry |
| condition inputs | causal feature values used |
| baseline intended size | 1.0× |
| incremental intended size | +0.25× (stated mult 1.25×) |
| actual fills | broker fills at intended sizes |
| incremental realized P&L | 0.25× sleeve only |
| incremental stress / MAE | sleeve path |
| whole-book stress and drawdown | baseline + incremental combined |
| parity mismatch reason | if intended ≠ filled |

**Do not stack yet** — no simultaneous multi-book HP boosts; no micro+full
contract stacking on the same index sleeve.

---

## Prior-opposed overlap gate (required before any simultaneous HP)

Three prior-opposed candidates exist (ES / YM / NQ). Before allowing any
**simultaneous** HP multiplier across them, re-run:

```bash
python -m live.futures_intraday_hp_sizeup_compare --email
```

Pairs:

1. ES ST-age>180 HP dates ↔ YM overnight-middle HP dates  
2. ES ST-age>180 HP dates ↔ NQ normal-OR HP dates  
3. YM overnight-middle HP dates ↔ NQ normal-OR HP dates  

Report (see `prior_opposed_overlap_report.csv`):

- shared HP dates  
- same-direction rate  
- incremental P&L correlation  
- incremental joint stress / MTM DD  
- worst simultaneous loss  
- margin at simultaneous boosted positions (`simultaneous_boosted_extra_units`)

**Until that joint gate is explicitly cleared for simultaneous boosts,
implement: at most one prior-opposed HP multiplier across ES/YM/NQ per session.**

Current read (research tape): ~15–16 shared dates, high same-dir (75–100%),
low incremental correlation (~0.04–0.11), gate = `HOLD_ONE_HP_PER_SESSION`.

---

## Portfolio / sleeve rules

- One HP multiplier per economic index sleeve per session (no NQ+MNQ / YM+MYM / ES+MES).  
- No same-regime ST+PMC stacking without a separate overlap pass.  
- Tier C stays shadow-annotation only (no order-size change).  
- Tier A/B: shadow first if lot geometry cannot express 1.25× cleanly; then
  controlled paper with incremental sleeve ledger above.

---

## Repeatable drivers

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"

# Full study: select → profile → 1.25× nulls → LIVE_PLAN
python -m live.futures_intraday_hp_sizeup_v1 --email

# Nulls only (reuse profile tape)
python -m live.futures_intraday_hp_sizeup_nulls --email

# Baseline vs 1.25/2/3/4× + prior-opposed overlap
python -m live.futures_intraday_hp_sizeup_compare --email
```

Skill: `potions-futures-intraday-hp-sizeup`.
