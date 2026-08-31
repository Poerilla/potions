# USDJPY Candidate Causality Review — 2026-08-24

Scope:

- **USDJPY Asia-range London filtered `S_3_1_3`** (`Jan skip + roll50 WR/PF`)
- **USDJPY Monday OR `M2_S3_R1`** baseline and Phase 2 core (`sitout +3` + skip Aug/Sep)

This review checks for lookahead / non-causal timing in the saved StrategyPlugin
folders and reruns the Monday OR targets after adding feature snapshots to
`monday_or_breakout`.

## Verdict

| Candidate | Verdict | Current performance | Causal evidence |
|---|---|---:|---|
| USDJPY Asia-range London filtered `S_3_1_3` | **PASS at 1m bar resolution** | **$178,142 / -$24,627 / 7.23 N/S** | 3,772 feature snapshots, 0 causality violations, 0 entry fills at/before activation, min entry delay 1m |
| USDJPY Monday OR `M2_S3_R1` baseline | **PASS at 15m bar resolution** | **$222,199 / -$26,821 / 8.28 N/S** | Fresh rerun, 13,722 feature snapshots, 0 causality violations, 0 entry fills at/before activation, every entry fills on the next 15m bar |
| USDJPY Monday OR `M2_S3_R1` Phase 2 core | **PASS at 15m bar resolution** | **$293,966 / -$27,726 / 10.60 N/S** | Fresh rerun, 11,010 feature snapshots, 0 causality violations, 0 entry fills at/before activation, every entry fills on the next 15m bar |

## What Was Checked

### Asia-Range London

- Asia range is precomputed from the prior 19:00 through current 03:00-exclusive window.
- The strategy starts at London 03:00 with `session_or_ranges` already known.
- Entry stops are OCO stop orders with `live_after_ts` set to the 03:00 decision bar.
- PaperBroker requires `bar.ts > live_after_ts`, so the earliest possible fill is 03:01.
- Filtered `S_3_1_3` state:
  - `orders.csv`: 5,640 rows
  - `fills.csv`: 1,924 rows
  - `feature_snapshots.csv`: 3,772 rows
  - `causality_violations.csv`: header only
  - Entry fill activation audit: **0** entry fills at/before `live_after_ts`
  - Entry delay: min **1m**, median **97m**, max **538m**

The rolling WR/PF gate is not a future-looking equity filter in the implementation:
the offline gate builder uses only prior campaigns, and the live plugin gate uses
the shadow book as of the current session. The existing validation hub also keeps
`validation_decision_tape.csv`, filter attribution, OOS rows, and filter nulls.

Residual limitation: this is still a 1m OHLC broker replay, not a tick-queue proof.

### Monday OR

The Monday OR driver uses 15m bars for both signal and fills. This avoids the
previous HTF+1m bug class where an hourly signal bar was allowed to fill inside
its own lower-timeframe tape. Here, a signal on a 15m bar emits a market intent
with `live_after_ts = signal_bar.ts`; PaperBroker then requires the fill bar to
have `bar.ts > live_after_ts`, so entries occur on the next 15m bar.

Fresh feature snapshots added to `monday_or_breakout`:

- `monday_or_range`: Monday high/low, `R`, and the timestamp of the range fact.
- `monday_or_breakout_gate`: the 15m close breakout used for the entry decision.
- `monday_or_htf_filter`: the last completed 1h MA/OBV filter state used by the gate.

Fresh rerun folders:

- Baseline: `live/state/monday_or_sizing_sweep_broker_usdjpy/states/usdjpy_m2_s3_r1`
- Phase 2 core: `live/state/monday_or_phase2/tuneup_broker/states/usdjpy_m2_s3_r1_tuneup`

Mechanical audit:

- Baseline: 11,889 orders, 6,638 fills, 13,722 feature snapshots, **0** violations.
- Phase 2 core: 9,466 orders, 5,269 fills, 11,010 feature snapshots, **0** violations.
- Entry fills at/before `live_after_ts`: **0** in both folders.
- Entry delay: min/median/max **15m / 15m / 15m** in both folders.

Residual limitation: this is causal at 15m bar resolution. It is not yet a
1m/tick-path proof for intra-15m stop/limit ambiguity.

## Rerun Notes

- The baseline `M2_S3_R1` row was rerun from full USDJPY history after snapshot instrumentation.
- The old cached baseline was **$218,890 / -$26,688 / 8.20 N/S**.
- The fresh baseline is **$222,199 / -$26,821 / 8.28 N/S**.
- The Phase 2 core remains **$293,966 / -$27,726 / 10.60 N/S**.

## Do Not Overclaim

- Asia-range London is **research/practice promote**, not funded-sleeve ready.
- Monday OR Phase 2 is **hardened / live-paper eligible**, but still needs live
  broker parity and execution slippage tracking.
- Neither result is a tick-level queue proof.
