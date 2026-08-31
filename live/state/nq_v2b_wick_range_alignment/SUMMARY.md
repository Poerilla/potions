# NQ V2B × WICK_REJECT range-seed alignment (causal state label)

**Updated:** 2026-08-30 12:50 ET
**Hub:** `live/state/nq_v2b_wick_range_alignment/`
**V2B book:** prior-opposed resting-limit hour-complete (`S_1_1_3`).
**Structure:** frozen NQ WICK_REJECT range seeds (break direction label; retest fill NOT required).
**Mode:** FULL

## Stance

**DESCRIPTIVE ONLY** — OPPOSED_BREAK is **not** harmful on this book (n=22): avg $/trade **+$1,809** vs ALIGNED **+$1,098** and NO_ACTIVE_SEED **+$3,248**. Skip-opposed CF **not run** (would remove a better-than-aligned sleeve). No size-up; no hybrid P&L; no plugin yet.

Coverage note: only **53/439** campaigns sit under an active resolved seed (31 aligned + 22 opposed); **381** are NO_ACTIVE_SEED — the structure label is sparse relative to the V2B book.

## Causal rule

```
if structure.break_available_at < V2B.order_active_ts: usable
else: unavailable
```

Active seed window: `available_at < order_active_ts <= expires_at`.
Most recent active seed wins. No post-entry retest fill filter.

## Structure seed count

| Metric | Value |
|---|---:|
| Frozen seeds with path state | 91 |
| V2B primary campaigns | 439 |

## Core comparison (NQ primary)

| State | n | net $ | stress $ | N/S | WR | PF | avg R | med R | TP1/2/R% | stop% | L/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALIGNED_BREAK | 31 | +34042 | -27365 | 1.24 | 58% | 1.41 | +0.189 | +0.204 | 35/19/26 | 42% | 19/12 |
| OPPOSED_BREAK | 22 | +39795 | -16390 | 2.43 | 64% | 1.68 | +0.312 | +0.245 | 50/18/27 | 45% | 8/14 |
| UNRESOLVED_SEED | 5 | +31002 | +0 | 99.00 | 80% | 8.69 | +1.070 | +1.694 | 80/40/60 | 40% | 4/1 |
| NO_ACTIVE_SEED | 381 | +1237318 | -55318 | 22.37 | 66% | 2.44 | +0.560 | +0.311 | 57/25/44 | 48% | 159/222 |
| ALL | 439 | +1342158 | -55318 | 24.26 | 66% | 2.34 | +0.528 | +0.283 | 56/24/42 | 47% | 190/249 |

## Secondary MNQ (execution-scale confirmation)

| State | n | net $ | WR | PF | avg net |
|---|---:|---:|---:|---:|---:|
| ALIGNED_BREAK | 30 | +3706 | 60% | 1.47 | +124 |
| OPPOSED_BREAK | 21 | +4684 | 67% | 1.90 | +223 |
| NO_ACTIVE_SEED | 373 | +117007 | 66% | 2.34 | +314 |
| ALL | 428 | +128360 | 65% | 2.27 | +300 |

## Guardrails

- No size-up on ALIGNED_BREAK.
- No hybrid wick-retest + V2B P&L portfolio.
- No joint tuning of seed width / V2B conditions.
- Retest-fill states deferred (sample too selective).
