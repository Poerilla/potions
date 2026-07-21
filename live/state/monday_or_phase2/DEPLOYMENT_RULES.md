# Monday OR Phase 2 — live deployment rules

**Status:** Phase 2 complete — core + extended ex-silver (2026-07-21).  
**Excluded:** XAGUSD (Phase 1 reject).

## Funding gates (paper → live)

| Pair | Tag | Min Net/Stress | Min PF | Worst-year DD gate | Robustness / stance |
|---|---|---:|---:|---|---|
| **USDJPY** | `M2_S3_R1` | **≥ 4.0** | ≥ 1.15 | ≤ baseline worst year × 1.2 | Sub-periods **PASS** 3/3 → **live/paper eligible** |
| **USDJPY** | `M2_S3_R2` | ≥ 4.0 | ≥ 1.15 | same | Dollar alternate |
| **AUDJPY** | `M1_S2_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **PASS** 3/3; clustering FLAG → **small satellite only** |
| **XAUUSD** | `M2_S2_R3` | ≥ 1.5 | ≥ 1.15 | same + **stress budget** | Sub-periods PASS 2/3; heat −$230k → **default do-not-fund** / opportunistic |
| **EURUSD** | `M1_S2_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **FAIL** → **paper-only** |
| **GBPUSD** | `M1_S1_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **FAIL** → **paper-only** |
| **XAGUSD** | — | — | — | — | **Excluded** |

### Operational read

- **Primary book:** USDJPY Monday OR under caps below.
- **Satellite (optional):** AUDJPY at small size if clustering concentration is accepted.
- **Paper-only:** EURUSD, GBPUSD until post-2019 slices recover.
- **Gold:** dollars exist but heat dominates — not a core sleeve; silver stays out.

## Initial capital caps

| Sleeve | Initial notional equiv. | Rationale |
|---|---|---|
| USDJPY Monday OR | **3–5M** | Strongest N/S (8.20) |
| AUDJPY Monday OR | **0.5–1.5M** | Satellite; smaller edge |
| EURUSD / GBPUSD | **1–2M / 2–3M paper band** | Reserved; live blocked on sub-period fail |
| XAUUSD | **≤1M** if ever | Stress-budget limited |
| XAGUSD | **0** | Excluded |
| Futures intraday | Separate book | Not fungible with FX Monday OR caps |

## Scaling rule

Increase notional by **1.5×** only after **6–12 months** live (or funded paper) performance stays within:

- Backtest Net/Stress band: ≥ 80% of Phase 1 broker N/S for that tag
- Drawdown band: live max DD ≤ 1.2 × backtest stress |DD|

If either band breaks: freeze size, review, do not scale.

## Do-not-cross-use

- EURUSD / AUDJPY → **`M1_S2_R2`** (light shifted) — pair-specific live decisions still apply.
- GBPUSD → **`M1_S1_R2`** (matched sidecar).
- USDJPY → **`M2_S3_R1` / `M2_S3_R2`** only.
- XAUUSD → **`M2_S2_R3`** only if stress-approved; never copy onto FX majors.
- Never transplant USDJPY heavy sizing onto EUR/GBP/AUD.

## Config source

Pair-tag knobs: [`live/monday_or_phase2_tags.py`](../../monday_or_phase2_tags.py).  
Broker driver: [`live/fx_monday_or_breakout_broker.py`](../../fx_monday_or_breakout_broker.py).  
Specs: `SPEC_*.md` in this folder.

## Phase 3

USDJPY-first track-record; optional AUDJPY satellite; EUR/GBP re-entry only after regime pass; gold opportunistic only; silver out.
