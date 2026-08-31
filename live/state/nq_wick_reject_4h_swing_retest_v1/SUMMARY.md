# NQ WICK_REJECT 4h swing retest v1 — Stage A (S1)

**Updated:** 2026-08-30 13:45 ET
**Hub:** `live/state/nq_wick_reject_4h_swing_retest_v1/`
**strategy_id:** `nq_wick_reject_4h_swing_retest_v1`
**Model S1:** 4h WICK_REJECT seed → later **4h close** outside → limit retest **seed boundary** → opposite-edge stop ±1 tick → 0.5W/1W/2W 50/25/25.
**Horizon:** seed expiry **30 × 4h**; primary order life **48h** (mechanical translation).
**Compare-to:** 1h confirm + 24h life — 67 fills, dev avg R +0.177, holdout avg R −0.036.
**Structure engine:** identical atlas `StructureProgramEngine_v1_existing` (no permissive redo).
**Mode:** FULL

## Phase 0 — timing census

| Metric | Value |
|---|---:|
| Atlas 4h WICK_REJECT (pen≥0.05) | 122 |
| Eligible seeds (width/early/dedupe) | 91 |
| Rejected | 31 |
| Any 4h close break before seed expiry | 91 |
| Seed expired before break | 0 |
| Atlas bullish CLOSE_BREAK in seed window | 41 |
| Atlas bearish CLOSE_BREAK in seed window | 28 |

Reject reasons: `{"duplicate_confirm_bar": 17, "width_gt_2.00_ATR": 12, "early_close_session": 2}`

Among breaks: retest≤24/48/72h = **53 / 56 / 58** of 91; both-sides-break flag = **48**; break-expired-before-retest (48h) = **35**.

## Stage A — S1 primary (48h) vs 1h baseline

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| life_24h_ALL | 91 | 53 | 58% | +25360 | +478 | 55% | 1.74 | +0.125 | +0.249 | 58% | 72/53/40 | 30/23 |
| s1_4h_close_48h_dev | 74 | 43 | 58% | +9316 | +217 | 56% | 1.37 | +0.120 | +0.249 | 58% | 70/53/40 | 25/18 |
| s1_4h_close_48h_holdout | 17 | 13 | 76% | +7925 | +610 | 46% | 1.44 | +0.038 | -0.250 | 62% | 69/46/38 | 6/7 |
| s1_4h_close_48h_ALL | 91 | 56 | 62% | +17241 | +308 | 54% | 1.40 | +0.101 | +0.248 | 59% | 70/52/39 | 31/25 |
| life_72h_ALL | 91 | 58 | 64% | +21967 | +379 | 55% | 1.51 | +0.126 | +0.248 | 59% | 71/53/40 | 32/26 |

## Stance

**RESEARCH — S1 positive locked avg R both slices (S2 gate OPEN; not promote)**

- Identical seed population / atlas slice as the completed 1h model (expiry wall differs: 30 vs 20).
- S2 run as separate candidate (see Stage C).
- If fills < ~40–50, treat P&L as descriptive only.

## Guardrails

- No new 4h swing definition; atlas engine only.
- No mixing S1/S2 levels.
- No expiry tuning until first causal locked result known.
- One trade per seed; no re-entry; no adds.

## Stage C — S2 (new post-seed 4h swing level)

First atlas `CLOSE_BREAK` after seed; trade only if break_level outside seed; limit at **new swing level**; stop at opposite **original seed** boundary; 48h life.

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| s2_new_swing_48h_dev | 74 | 24 | 32% | +6386 | +266 | 67% | 1.51 | -0.024 | +0.171 | 33% | 79/67/38 | 15/9 |
| s2_new_swing_48h_holdout | 17 | 4 | 24% | +10212 | +2553 | 100% | inf | +0.254 | +0.197 | 0% | 100/75/25 | 2/2 |
| s2_new_swing_48h_ALL | 91 | 28 | 31% | +16597 | +593 | 71% | 2.34 | +0.015 | +0.174 | 29% | 82/68/36 | 17/11 |

**S2 stance:** DESCRIPTIVE ONLY — S2 fills <40

Non-fill / terminal reasons (top): `{"no_qualifying_first_swing_break": 40, "limit_life_or_age_no_fill": 23, "stop@5426.25\u00d71.00": 1, "TP1@16111.12\u00d70.50;TP2@16159.50\u00d70.25;expiry_flat@16064.50\u00d70.25": 1, "TP1@11018.88\u00d70.50;TP2@10971.00\u00d70.25;TP3@10875.25\u00d70.25": 1, "TP1@10901.88\u00d70.50;expiry_flat@10802.25\u00d70.50": 1, "TP1@11930.38\u00d70.50;TP2@11725.50\u00d70.25;expiry_flat@12594.00\u00d70.25": 1, "stop@14888.75\u00d71.00": 1}`

S1 and S2 are **not** combined — separate trial-ledger candidates.
