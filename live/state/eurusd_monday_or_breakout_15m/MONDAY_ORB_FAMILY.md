# EURUSD Monday ORB family — capital-efficiency ranking

**Primary yardstick:** broker-like **Net/Stress** when available; else pandas Net/|Closed DD|.  
Fee $1.50/unit, PV $100k. HTF both-opposed + parallel shifted primary unless noted.

**Research log:** [`RESEARCH.md`](RESEARCH.md)  
**Broker sizing sweep:** [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md)  
**Phase 2 hardening:** [`../monday_or_phase2/SUMMARY.md`](../monday_or_phase2/SUMMARY.md)  
**Pandas sizing sweep:** [`../monday_or_sizing_sweep/INDEX.md`](../monday_or_sizing_sweep/INDEX.md)  
**Cross-pair broker (pre-sweep M1_S1_R1):** [`../fx_monday_or_breakout_broker/SUMMARY.md`](../fx_monday_or_breakout_broker/SUMMARY.md)

## Broker-confirmed sizing (Phase 1, all FX + metals, 2026-07-21)

| Rank | Pair / tag | ≈USD Net | Stress DD | **N/S** | Structure |
|---:|---|---:|---:|---:|---|
| 1 | **USDJPY `M2_S3_R1`** | +$219k | −$27k | **8.20** | Main 3=(1@30,2@50), shifted 4, max 2/week |
| 2 | **GBPUSD `M1_S1_R2`** | +$231k | −$87k | **2.67** | Main 3=(2@30,1@50), shifted 3, max 3/week |
| 3 | XAUUSD `M2_S2_R3` | +$438k | −$230k | **1.90** | Dollars yes, heat huge |
| 4 | AUDJPY `M1_S2_R2` | +$96k | −$52k | **1.83** | Same recipe as EURUSD |
| 5ᵉ | **EURUSD `M1_S2_R2`** | +$123k | −$71k | **1.74** | Beats ST+PMC 1.49 |
| — | XAGUSD best | −$224k | −$230k | **−0.97** | Reject |

Hub: [`../monday_or_sizing_sweep_broker/INDEX.md`](../monday_or_sizing_sweep_broker/INDEX.md).

## EURUSD pandas family (context)

| Rank | Model | Net | Closed DD | Net/\|DD\| | Notes |
|---:|---|---:|---:|---:|---|
| 1 | `M1_S2_R2` (pandas) | +$179k | −$54k | **3.28** | Confirmed #1 under broker too |
| 2 | `M1_S1_R1` shifted match | +$125k | −$56k | 2.21 | Pre-sweep default |
| 3 | 1-lot fade parallel | +$118k | −$60k | 1.98 | |
| 4 | Primary only | +$103k | −$54k | 1.92 | |

## Read / promotion stance (Phase 2 complete — core + extended)

- **USDJPY default:** `M2_S3_R1` — live/paper under 3–5M.
- **AUDJPY satellite:** `M1_S2_R2` — sub-periods PASS; small optional sleeve.
- **EURUSD / GBPUSD:** paper-only (sub-period FAIL post-2019).
- **XAUUSD:** heat caution / default do-not-fund; **XAGUSD excluded**.
- Do not cross-use recipes across pairs.

*Updated 2026-07-21 — Phase 2 extended (ex-silver).*
