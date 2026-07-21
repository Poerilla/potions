# SPEC — XAUUSD Monday OR `M2_S2_R3`

**Status:** Phase 2 extended · sub-periods **PASS** (2/3) · **heat caution**.  
**Plugin:** `monday_or_breakout` · silver (**XAGUSD**) explicitly **excluded**.

## Logic (plain English)

Monday OR breakout + shifted primary on gold. Runner-heavier main (1@30, 2@50), light shifted sidecar (2), **unlimited** primary/week (`R3`). HTF both-opposed skip.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M2` | Main 3 = 1@30%, 2@50% |
| `S2` | Shifted 2 = 1@30%, 1@50% |
| `R3` | Unlimited primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$438k |
| Stress DD | −$230k |
| **Net/Stress** | **1.90** |
| Baseline `M1_S1_R1` | 1.04 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 2/3 |
| Clustering | FLAG — top week ~19%; fat-tail weeks |
| Heat | Stress ~−$230k — CE fragile despite dollars |
| DD sensitivity | **PASS** — 25/45 N/S 1.55 (−19%); 35/55 N/S 1.66 (−13%) |

## Capacity sketch

Not a clean FX sleeve. If funded at all: **≤1M** notional equivalent, stress-budget limited, separate from FX Monday OR caps. Prefer treating as research / opportunistic, not core CTA allocation.

## Do-not-cross-use

Do not copy `M2_S2_R3` onto FX majors. Do not revive XAGUSD under this tag (Phase 1 reject).

## Deployment

Gate: N/S ≥ 1.5 **and** explicit stress budget approval. Default stance: **do not fund** alongside USDJPY core until heat is reduced (size cut or filter).
