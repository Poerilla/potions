# US30 PMC failed-break / liquidity-sweep fade (v1)

**Status:** Phase 1/2 COMPLETE — RESEARCH_WEAK_POSITIVE (confirmed net+$2.6k N/S 0.81; no promote).

**Hub:** `live/state/us30_pmc_failed_break_fade/`

**Motivation:** Signal-hour attribution shows ~90% post-close PMC retest after old ST+PMC signals, but causal Path B (retest) is negative on full history. Do **not** fade the ST+PMC signal. Test a stricter failed-break sequence on pre-known **PMC only**.

## Hypothesis (frozen)

```text
Pre-known PMC
→ sweep beyond level (MIN_PENETRATION)
→ 5m close back inside (failure, ≤60m)
→ next 5m confirms rejection
→ one fixed fade entry (next 1m open)
→ structural stop beyond sweep ± 1 tick
→ scale-out 50%@1R / 25%@2R / 25%@4R runner
→ no averaging down / no add in v1
```

## Frozen parameters

| Param | Value |
|---|---|
| Level | Prior month close (PMC) only |
| Signal TF | Completed 5m |
| Fill TF | Next 1m open after confirmation |
| MIN_PENETRATION | 0.10 × ATR_20_5m |
| MAX_FAILURE_MINUTES | 60 |
| CONFIRMATION_BARS | 1 |
| STOP_BUFFER | 1 native tick |
| TP ladder | 1R / 2R / 4R (50/25/25) |
| Max trades | 1 per level per session |
| SESSION_CUTOFF | 15:00 NY |
| EOD_FLATTEN | 15:55 NY |
| Early closes | excluded |
| Fills | 1m stop-first + adverse entry/stop + OANDA-style costs |

## Controls (predeclared)

| Control | Rule |
|---|---|
| Naive fade | Fade first PMC sweep; no reclaim |
| Reclaim-only | First 5m close back inside; no confirmation bar |
| v1 confirmed | Reclaim + follow-through confirmation (primary) |

## Phases

1. **Event taxonomy** — descriptive table of all PMC sweeps (penetration, time beyond, reclaim windows, MFE/MAE, hour/DOW/event) before P&L.
2. **Frozen base replay** — v1 + two controls; US30 full history; no extra filters.
3. **Causality + bounded sensitivity** — persist timestamp chain; plateaus on penetration / deadline / runner / stop / entry delay.
4. **Adversarial report** — yearly incl. 2020/2022, L/S split, top-k, LOYO, slippage stress, overlap vs surviving NQ books.

## Scale-in / scale-out

- v1: **scale-out only**, one fixed unit, no add while losing.
- Optional add only after base is positive/stable/causal: after TP1, retest of reclaimed PMC from valid side, stop at BE / retest extreme.

## Interpretation gates

| Result | Action |
|---|---|
| Confirmed fade negative | Retire US30 revival program |
| Reclaim-only + / confirmed − | Do not promote; separate early-entry study only if warranted |
| Confirmed + stable plateau | StrategyPlugin port |
| Naive + / confirmed − | Suspect artifact; do not promote |
| Runner drives all net | Keep runner dependence explicit; capped exits before demo |

## Queue trigger

See `QUEUE.sh` — waits for revival pid, then launches Phase 1 taxonomy driver (or agent) with `--email`.

Source plan: user prompt 2026-08-29 (failed-PMC-break fade family).

## Follow-on (queued)

Structure-bias alignment overlay:
[`../us30_pmc_failed_break_fade_structure_bias/RESEARCH_PLAN.md`](../us30_pmc_failed_break_fade_structure_bias/RESEARCH_PLAN.md)
(DSR `TRL-2026-00189`).
