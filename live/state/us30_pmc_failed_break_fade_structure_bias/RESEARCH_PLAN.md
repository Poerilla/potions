# US30 PMC confirmed fade × 4h structure-bias alignment

**Status:** Phase 1/2 COMPLETE — ARCHIVE_OVERLAY.
**Hub:** `live/state/us30_pmc_failed_break_fade_structure_bias/`
**Parent:** `live/state/us30_pmc_failed_break_fade/` (DSR `TRL-2026-00187`, confirmed N=129 net+$2612 N/S 0.81)
**DSR (this trial):** `TRL-2026-00189`
**Stance target:** RESEARCH only — eligibility filter, not size-up / not demo until gates clear.

## Motivation

Confirmed PMC failed-break fade is weak-positive (not negative). Hypothesis:

```text
Countertrend sweep → reclaim + 5m confirm → fade aligns with
prevailing higher-timeframe StructureProgramEngine bias.
```

This is a **narrow pre-registered overlay**, not an open filter search.

## Frozen base (unchanged from parent)

Reuse parent confirmed fade exactly:

| Param | Value |
|---|---|
| Level | PMC only |
| Signal | 5m reclaim + 1 confirmation bar ≤60m |
| Entry | next 1m open after confirmation |
| Stop | sweep extreme ± 1 tick |
| Scale-out | 50%@1R / 25%@2R / 25%@4R (2/1/1 lots) |
| Costs | fee $1.50/unit + 1-tick adverse entry/stop |
| Early closes | excluded |

**Do not** rebuild structure logic. Use existing `StructureProgramEngine` on **completed 4h** bars (`live.structure_program_st_chart_bias_4h.to_4h` + `_ingest_4h_day`).

## Bias mapping

| Engine `program` | Bias label |
|---|---|
| `buy` | `BULLISH` |
| `sell` | `BEARISH` |
| `None` and `ready` | `NEUTRAL` |
| not `ready` / no completed 4h yet | `UNAVAILABLE` |

Availability must be causal:

```text
structure_bar_end_ts
structure_feature_available_at  ≤  fade_confirmation_close_ts
  < entry_submit_ts ≤ entry_fill_ts
```

Use **last completed 4h structural state before confirmation close** only.

## Alignment classification

| Bias at confirm | Fade side | Alignment |
|---|---|---|
| BULLISH | LONG | `ALIGNED` |
| BULLISH | SHORT | `OPPOSED` |
| BEARISH | SHORT | `ALIGNED` |
| BEARISH | LONG | `OPPOSED` |
| NEUTRAL | either | `NEUTRAL` |
| UNAVAILABLE | either | `UNAVAILABLE` |

Economic read: fade a **failed countertrend break** so the reversal returns price toward the structural direction. Do **not** re-interpret as “fade with the sweep.”

## Phase 1 — descriptive event study (no filter)

Run **all** confirmed fades unchanged; label each campaign; report:

| Group | N | Net | N/S | PF | WR | Median R | MAE | MFE | 1R | 2R | 4R | runner_share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALIGNED | | | | | | | | | | | | |
| OPPOSED | | | | | | | | | | | | |
| NEUTRAL | | | | | | | | | | | | |
| UNAVAILABLE | | | | | | | | | | | | |

Also split ALIGNED into bullish+long vs bearish+short.

## Phase 2 — three fixed strategy variants only

```text
baseline          — all confirmed fades
aligned_only      — ALIGNED only
aligned_plus_neut — ALIGNED + NEUTRAL (skip OPPOSED only)
```

**Forbidden in this trial:** bullish-only / bearish-only books, daily vs 4h swaps, swing-length changes, ATR/RSI overlays, size-up, scale-in.

## Scale-out robustness (diagnostics, not optimization)

For each alignment group and each Phase-2 variant, also report:

1. Full 1R/2R/4R plan (base)
2. No-runner cap: all exits at 2R
3. Reduced runner: 50%@1R / 50%@2R

Question: do ALIGNED fades reach 1R/2R often enough without needing rare 4R?

## Phase 3 — action selection (only if Phase 2 clears)

If ALIGNED lifts N/S with lower stress and stable periods:

```yaml
confirmed_pmc_fade:
  if_structure_bias_aligned:
    trade: true
    size: 1.00x
  if_structure_bias_opposed:
    trade: false
  if_structure_bias_neutral:
    shadow_log: true
```

Eligibility filter only — **no 1.25×**. If OPPOSED wins, mark discovery; do not invent a story.

## Robustness (after Phase 2 if lift looks real)

- Full-history + calendar blocks
- Long / short separately
- Top-1 / top-3 / top-5 campaign share
- Leave-one-year-out N/S
- 1 / 2 / 4 tick stop-slip; 2× / 3× cost
- 1m / 2m entry delay
- Early-close exclusion (already on)
- Causality timestamp chain persisted per trade

## Decision gates

| Result | Action |
|---|---|
| ALIGNED N/S ≤ baseline or negative | Archive overlay; close fade workstream if no other path |
| ALIGNED improves but N ≲ 50 | Shadow only; no demo |
| ALIGNED improves, lower stress, stable, runner share not worse | StrategyPlugin port candidate |
| aligned+neutral works, aligned-only does not | Consider OPPOSED-skip throttle |
| One directional branch drives all benefit | Descriptive only until separately validated |
| Runner removal collapses result | No demo until tail dependency characterized |

## Implementation notes

- Driver: prefer extending `live/us30_pmc_failed_break_fade.py` with `--phase structure_bias` **or** new `live/us30_pmc_failed_break_fade_structure_bias.py` that reuses confirmed-trade generation / fills.
- Reuse parent confirmed trades tape where possible (`replay/confirmed/trades.csv`) and attach causal 4h bias at `confirm_ts`; re-aggregate P&L by group / filtered variants (same fills — no re-optimization).
- If regenerating fills, must match parent frozen params bit-for-bit.
- `--email` + `live.run_ledger` (`run_class=pandas` or `ha` / `other` as appropriate; note parent DSR).
- Append DSR `TRL-2026-00189` **before** peeking metrics.
- Write `SUMMARY.md`, `EMAIL.txt`, alignment CSV, variant metrics.

## Explicitly out of scope (this queue)

- Scale-in / averaging down
- Winner-add after TP1 (future only if aligned-only clears)
- Hourly structure (use 4h only)
- Second structure engine / parameter retune

Source: user plan 2026-08-29 (structure-bias overlay on confirmed PMC fade).
