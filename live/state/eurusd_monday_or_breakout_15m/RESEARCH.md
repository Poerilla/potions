# EURUSD / FX Monday OR breakout — research log

**Status (2026-07-21):** Phase 2 hardening **complete**. USDJPY `M2_S3_R1` is the default live/paper Monday OR candidate; EURUSD `M1_S2_R2` is paper-only pending recent-regime fix. Phase 1 broker sizing across all six instruments remains the map.

**Hub docs**
- Family CE ranking: [`MONDAY_ORB_FAMILY.md`](MONDAY_ORB_FAMILY.md)
- Broker sizing sweep: [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md)
- Phase 2 hardening: [`../monday_or_phase2/SUMMARY.md`](../monday_or_phase2/SUMMARY.md)
- Broker cross-pair (pre-sweep): [`../fx_monday_or_breakout_broker/SUMMARY.md`](../fx_monday_or_breakout_broker/SUMMARY.md)
- STRATEGY_TRACKER Forex section: [`../../../mnq/case_studies/STRATEGY_TRACKER.md`](../../../mnq/case_studies/STRATEGY_TRACKER.md)
- Plugin: `live/strategies/monday_or_breakout.py`
- Research driver: `live/eurusd_monday_or_breakout_15m.py`
- Broker driver: `live/fx_monday_or_breakout_broker.py`
- Broker sizing driver: `live/monday_or_sizing_sweep_broker.py`

---

## Goal

Find a capital-efficient **weekly Monday opening-range** breakout on FX 15m that survives HTF filters and broker realism, then check whether it generalizes beyond EURUSD.

---

## Research path (steps that made it viable)

### 1. Thin-edge baseline (rejected as final)

- Mon H/L OR → Tue–Fri 15m close breakout → 1 lot, SL=1R, TP=2R, max 2/week.
- ~+$33k / −$27.5k closed ≈ **1.21** Net/|DD|. Edge real but thin.

### 2. Sizing / DD-cut ladder (kept)

Tested multi-lot structures; **runner past 50% DD hurt CE**. Settled on:

| Structure | Result |
|---|---|
| 2-lot, cut 1 @ 50% | ~0.95 CE — worse |
| 3-lot, cut@30 + cut@50, last to full SL | ~1.16 CE — runner hurt |
| **3 in → drop 2 @ 30% DD → cut last @ 50% (flat, no runner)** | **Primary backbone** |

Primary-only (no sidecar): **+$102.7k / −$53.6k / 1.92**.

### 3. Day-of-week filters (rejected)

Day filters on Tue–Fri **hurt** edge. Kept **no day filter**.

### 4. HTF filter (kept)

Skip entry when last completed **1h** bar has **both** MA50/150 and OBV vs OBV-SMA20 **opposed** to the trade. Survived loser-cluster analysis (`eurusd_monday_or_htf_loser_clusters.py`).

### 5. Reverse-fade sidecar experiments

| Variant | Net/\|DD\| | Verdict |
|---|---:|---|
| Parallel **1-lot** fade @ flat price + HTF | **1.98** | Strong; briefly #1 |
| Parallel **3-lot** structured fade + HTF | 1.77 | Best **$** (+$165k), worse CE |
| Blocking 1-lot fade | 1.39 | Opportunity cost |
| Boundary fade (enter at Mon extreme) | negative | Rejected |
| Fade-only (no primary) | negative | Rejected |

### 6. Shifted primary (current research #1)

**Idea:** instead of fading at the flat price after a failed break, take the **same primary structure** shifted by **one Monday range**:

- Failed long at Mon high → wait for **short** breakout of **Mon low**
- Failed short at Mon low → wait for **long** breakout of **Mon high**
- Same 3 / drop2@30 / cut1@50 / 1R–2R

| Wiring | Net/\|DD\| | Note |
|---|---:|---|
| Exclusive wait (blocks further primary) | 1.89 | Burns 2nd primary — rejected |
| **Parallel** (opposite extreme reserved; same-side primary OK) | **2.21** | **Research champion** |

State: `eurusd_monday_or_breakout_15m_shiftprim_htf/` (+$124.6k / −$56.4k closed).

### 7. Context charts (no trades)

Regenerated `eurusd_15m_pwh_pwl_pwc_charts/` — 150 random Mon–Fri weeks with **Mon high / mid / low** + PWH/PWL/PWC, **no SuperTrend**.

### 8. StrategyPlugin + broker battle test

Implemented `monday_or_breakout` plugin (15m, DD stops, shifted arm, HTF). Ran Engine + PaperBroker (1-tick slip, $1.50/unit, next-open market entry) on all `fx/raw` pairs:

| Pair | ≈USD Net | Stress | **N/S** |
|---|---:|---:|---:|
| USDJPY | +$138k | −$32k | **4.27** |
| GBPUSD | +$202k | −$108k | **1.87** |
| AUDJPY | +$59k | −$55k | 1.07 |
| XAUUSD | +$260k | −$249k | 1.04 |
| EURUSD | +$76k | −$92k | **0.83** |
| XAGUSD | −$195k | −$196k | −1.00 |

**Read:** Research CE on EURUSD does **not** survive broker realism. Absolute net still beats ST+PMC dollars on EURUSD, but heat is worse. **USDJPY / GBPUSD** are the viability story.

### 9. USDJPY win/loss chart pack

100 winners + 100 losers under `../fx_monday_or_breakout_broker/charts_usdjpy/{winners,losers}/` (driver `live/usdjpy_monday_or_broker_charts.py`).

### 10. Sizing sweep Phase 1

Adapted plan + 27-cell grid (M×S×R) on EURUSD and USDJPY. Winners:

| Pair | Tag | CE vs baseline |
|---|---|---|
| EURUSD | **`M1_S2_R2`** | **3.28** vs 2.21 |
| USDJPY | **`M3_S3_R2`** | **13.37** vs 8.90 |

Hub: [`../monday_or_sizing_sweep/INDEX.md`](../monday_or_sizing_sweep/INDEX.md).

### 11. Broker sizing sweep Phase 1 (2026-07-21)

All 27 cells × **EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD**. Ranked by ≈USD Net/Stress.

| Pair | Broker #1 | N/S | ≈USD net |
|---|---|---:|---:|
| USDJPY | **`M2_S3_R1`** | **8.20** | +$219k |
| GBPUSD | **`M1_S1_R2`** | **2.67** | +$231k |
| XAUUSD | **`M2_S2_R3`** | **1.90** | +$438k (stress −$230k) |
| AUDJPY | **`M1_S2_R2`** | **1.83** | +$96k |
| EURUSD | **`M1_S2_R2`** | **1.74** | +$123k |
| XAGUSD | `M2_S2_R3` | **−0.97** | fail |

Hub: [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md).

---

## What “viable” means here

| Bar | Pass? |
|---|---|
| Positive research CE on EURUSD with disciplined DD cuts | **Yes** (2.21 → pandas 3.28 at `M1_S2_R2`) |
| HTF filter that removes opposed losers | **Yes** |
| Sidecar that improves CE without killing primary | **Yes** (shifted parallel) |
| Broker-like EURUSD beats promoted ST+PMC (1.49) | **Yes** at **`M1_S2_R2` (1.74)**; no at pre-sweep 0.83 |
| Broker-like generalization on major FX | **Yes** (USDJPY baseline 4.27 → sized **8.20**; GBPUSD 1.87 pre-sweep) |
| Metals | Mixed (XAU ~1.0, XAG fail) |

**Promotion stance:** **USDJPY `M2_S3_R1`** is Phase 2 hardened and live/paper-eligible under deployment caps. **EURUSD `M1_S2_R2`** stays paper-only after Phase 2 (sub-period FAIL) despite beating ST+PMC on full-sample N/S. Pair-specific sizing — do not copy EURUSD light-sidecar onto USDJPY. Phase 3 = track-record.

---

## Code / state map

| Artifact | Path |
|---|---|
| Research sim | `live/eurusd_monday_or_breakout_15m.py` |
| Charts (EURUSD sample) | `live/eurusd_monday_or_breakout_15m_charts.py` → `…/charts_sample/` |
| HTF loser clusters | `live/eurusd_monday_or_htf_loser_clusters.py` |
| PWH/PWL/PWC + Mon OR charts | `live/eurusd_15m_pwh_pwl_pwc_charts.py` |
| StrategyPlugin | `live/strategies/monday_or_breakout.py` (registered) |
| Broker multi-pair | `live/fx_monday_or_breakout_broker.py` |
| Broker sizing sweep | `live/monday_or_sizing_sweep_broker.py` → `live/state/monday_or_sizing_sweep_broker/` |
| USDJPY W/L charts | `live/usdjpy_monday_or_broker_charts.py` |
| Family ranking | this dir `MONDAY_ORB_FAMILY.md` |
| Broker states | `live/state/fx_monday_or_breakout_broker/states/*_shiftprim_htf/` |

---

## Commands

```bash
# Research champion (pre-sweep default)
python3 -m live.eurusd_monday_or_breakout_15m --shifted-primary

# Sizing sweep Phase 1 (M1-3 × S1-3 × R1-3)
python3 -m live.monday_or_sizing_sweep --phase 1 --pairs EURUSD,USDJPY

# Broker-like all pairs
python3 -m live.fx_monday_or_breakout_broker

# Broker sizing confirm (Phase 1)
python3 -m live.monday_or_sizing_sweep_broker --pairs EURUSD,USDJPY

# USDJPY chart pack
python3 -m live.usdjpy_monday_or_broker_charts
```

### Broker sizing Phase 1 headline

See [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md).

- EURUSD **`M1_S2_R2`**: N/S **1.74** (pandas CE 3.28 confirmed #1 under broker).
- USDJPY **`M2_S3_R1`**: N/S **8.20** (pandas `M3_S3_R2` is broker #3).

*Updated 2026-07-21 — broker sizing sweep rankings.*
