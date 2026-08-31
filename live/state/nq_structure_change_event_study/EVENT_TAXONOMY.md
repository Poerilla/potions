# Event taxonomy — structure-change atlas

Frozen with `STRUCTURE_CHANGE_RESEARCH_CONTRACT.yaml`. Engine unchanged:
`StructureProgramEngine` (`live/structure_program_st_study.py`), 4h via
`to_4h` / `_ingest_4h_day` (`live/structure_program_st_chart_bias_4h.py`).

## Structures (existing)

| Bias | Pivot sequence | Protected swing (key) | Invalidate / takeout |
|---|---|---|---|
| Bullish | L → H → LL → HH | LL | Trade **below** LL |
| Bearish | H → L → HH → LL | HH | Trade **above** HH |

Swing confirm: left=2, right=2 on the structure timeframe. Feature known only
at the **close of the confirmation bar**.

## Event classes (non-overlapping)

Relative to the **last confirmed protected swing** on that timeframe.

| Event | Bullish case | Bearish case | Meaning |
|---|---|---|---|
| `CLOSE_BREAK` | Completed bar **closes above** protected swing high (for upward break of bearish HH key, or break of structure high under study — see note) | Closes **below** protected swing low | Confirmed structural break |
| `WICK_REJECT` | High exceeds level, close ≤ level | Low breaks level, close ≥ level | Sweep / rejection candidate |
| `CLOSE_RECLAIM` | First closes beyond, then closes back inside within fixed window | Same opposite | Failed confirmed break |
| `TOUCH_ONLY` | Reaches level but penetration < min buffer | Same | Control / noise |

**Protected-swing orientation (engine key):**

- Bull structure key = **LL** → relevant breach for invalidation / bearish break is **below** key.
- Bear structure key = **HH** → relevant breach for invalidation / bullish break is **above** key.

Additionally record **continuation breaks** of the confirming extreme (bull HH /
bear LL) as transition-type annotations (`LH-LL-HH` completion already embeds
the HH; subsequent retests of p4 use the same four classes).

## Penetration

\[
\text{penetration}_{R} = \frac{|\text{extreme} - \text{protected swing}|}{\mathrm{ATR}_{20,\text{same TF}}}
\]

- Primary cut: `penetration >= 0.05 ATR`
- Also emit zero-buffer rows for robustness / control

## Timestamps (causal)

| Field | Definition |
|---|---|
| `touch_ts` | First lower-TF (1m) bar that breaches the protected swing |
| `confirm_bar_open_ts` / `confirm_bar_close_ts` | Structure-TF bar that establishes close break, wick reject, or reclaim |
| `feature_available_at` | Instant the confirming bar is **complete** |
| `order_active_ts` | Must satisfy `feature_available_at < order_active_ts` |

Example (1h bar 09:00–09:59 NY): known at 10:00; earliest action 10:01 / next
executable minute. 4h: session-aligned bar close via exchange/CFD calendar.

## Expansion (predeclared)

Directional MFE / adverse MAE over fixed horizons. **Primary scoring direction
depends on event class** (see outcome-direction audit):

| Event class | Primary outcome direction |
|---|---|
| `CLOSE_BREAK` | Same as close break |
| `WICK_REJECT` | Opposite of wick breach |
| `CLOSE_RECLAIM` | Reclaim direction (opposite prior break) |
| `TOUCH_ONLY` | None — absolute excursion only |

Break-direction diagnostics retained as `break_*` columns.

**R units (both reported):**

- Event-study ATR unit: `1 × ATR_20` on the structure TF
- Structural-risk unit: `|entry − protected swing|` (wick: max with penetration)

Labels (in each unit, outcome direction):

- Short: MFE ≥ 1.0R within 60m
- Session: MFE ≥ 2.0R before first eligible RTH close
- Multi-session: MFE ≥ 3.0R within two eligible sessions
- Failed: opp-dir MAE ≥ 1.0R before 1.0R favorable

Post-close entries: session-1 = next RTH day (session and two-session windows
must not collapse).

## Controls

Matched non-event samples: same hour, weekday, volatility bucket, prior-bias
state. No raw open/close range averages without matching.

## Research questions (frozen)

1. Expansion vs matched controls?
2. Direction of expansion (new structure / prior trend / neither)?
3. Timing (NY buckets / DOW / WOM)?
4. Close confirmation vs wick?
5. Wick / reclaim as fade?
6. 1h incremental beyond 4h?
7. Portability across markets?

## Phase gate

Phases 1–4 = event study only. Phase 5 prototypes only after stable,
holdout-surviving signal. Do not merge continuation and fade hypotheses.
