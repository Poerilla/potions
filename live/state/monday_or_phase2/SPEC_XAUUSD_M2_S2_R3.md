# SPEC — XAUUSD Monday OR `M2_S2_R3`

**Status:** Phase 2 extended · sub-periods **PASS** (2/3) · heat reduced via core filters.  
**Plugin:** `monday_or_breakout` · silver (**XAGUSD**) explicitly **excluded**.

## Logic (plain English)

Monday OR breakout + shifted primary on gold. Runner-heavier main (1@30, 2@50), light shifted sidecar (2), **unlimited** primary/week (`R3`). HTF both-opposed skip.

**Core (locked, StrategyPlugin-audited):**

1. After realized Mon-week net ≥ **+100 gold pts**, sit out the rest of that week (no new primary/shifted entries; open trades still manage to TP/SL/`week_end`).
2. **No new entries in July, September, or December** (NY calendar) — `skip_entry_months=[7,9,12]`.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M2` | Main 3 = 1@30%, 2@50% |
| `S2` | Shifted 2 = 1@30%, 1@50% |
| `R3` | Unlimited primary/week |
| sitout | Rest-of-week after +100 pts realized |
| season | Skip Jul / Sep / Dec entries |

## Key metrics (StrategyPlugin broker)

| Metric | Phase 1 | +sitout100 | **+sitout100 + skip Jul/Sep/Dec (core)** |
|---|---:|---:|---:|
| ≈USD Net | +$438k | +$510k | **+$580k** |
| Stress / MTM DD | −$230k | −$215k | **−$172k** |
| **Net/Stress** | **1.90** | **2.37** | **3.37** |
| Units | 12139 | 11170 | 8388 |

vs Phase 1: **+1.47 N/S**, **+$142k** net, MTM DD **$58k shallower**.  
vs sitout-only: **+0.99 N/S**, **+$70k** net, MTM DD **$43k shallower**.

Artifacts: `tuneup_broker/states/xauusd_m2_s2_r3_tuneup/` (core),  
`tuneup_broker/states/xauusd_m2_s2_r3_sitout100_only/` (archive).

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 2/3 (pre-tune book) |
| Clustering | FLAG — fat-tail weeks remain; season skip removes soft Jul/Sep/Dec mass |
| Heat | Pre-tune stress −$230k; core −$172k |
| DD sensitivity | **PASS** on pre-tune sizing grid |

## Capacity sketch

Still not a clean FX sleeve. If funded: **≤1M** notional equivalent, stress-budget limited, separate from FX Monday OR caps. Core filters materially improved N/S; stance can move from pure research toward **opportunistic / small satellite** under stress budget — not USDJPY-class primary.

## Do-not-cross-use

Do not copy `M2_S2_R3` (or Jul/Sep/Dec skip) onto FX majors without a fresh pair study. Do not revive XAGUSD under this tag.

## Deployment

Gate: N/S ≥ 1.5 **and** explicit stress budget approval.

**Plugin core:** `plugin_config(..., pair="XAUUSD")` must include `week_sitout_after_pts=100` and `skip_entry_months=[7,9,12]`. Do not disable without a new broker study.
