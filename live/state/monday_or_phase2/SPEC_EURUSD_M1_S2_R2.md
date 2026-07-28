# SPEC — EURUSD Monday OR `M1_S2_R2`

**Status:** Phase 2 candidate · **paper-only** until sub-period gate passes.  
**Plugin:** `monday_or_breakout` · config via `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Each Monday defines an opening range (high/low). Tue–Fri, on 15m close, trade breakouts of that range (long above Mon high, short below Mon low). Enter 3 units with SL = 1R and TP = 2R. Cut 2 units at 30% of the way to the stop and flatten the last unit at 50% (no runner past 50% DD). After a primary flats at 50% DD, arm a **shifted primary** at the **opposite** Monday extreme (same DD ladder, lighter size). Skip entries when the last completed 1h bar has both MA50/150 and OBV vs OBV-SMA20 opposed to the trade. Cap at 3 primary entries per week.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30% DD, 1@50% DD |
| `S2` | Shifted 2 = 1@30% DD, 1@50% DD (lighter sidecar) |
| `R2` | Max **3** primary trades/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$123.3k |
| Stress DD | −$70.9k |
| **Net/Stress** | **1.74** |
| Baseline `M1_S1_R1` N/S | 0.83 |
| vs ST+PMC EURUSD | Beats 1.49 on full-sample N/S |

**Tune-up test (rejected):** skip-1-after-W → N/S 1.79 (−$11k net). Not core.

PF / win rate / worst year: see Phase 1 audit under `live/state/monday_or_sizing_sweep_broker/audits/eurusd_m1_s2_r2/`.

## Behaviour summary

Exploits Monday OR breakouts with early risk truncation and a light opposite-extreme second chance. EURUSD does **not** reward heavy runner or heavy sidecar sizing (those lag in Phase 1).

## Robustness (Phase 2)

| Check | Result |
|---|---|
| Sub-periods | **FAIL** — pre-2020 strong; 2020–2022 and 2023+ negative unit net |
| Clustering | FLAG — top week ~13% of lifetime |net| (2010-05-03) |
| Local R tweak | `M1_S2_R1` N/S 0.94 — worse; keep R2 |
| DD sensitivity | **PASS** — 25/45 N/S 2.35; 35/55 N/S 1.87 (vs 1.74) |

## Capacity sketch

Initial paper band **1–2M** notional equivalent. Major-pair FX liquidity is ample at this size; impact risk is secondary to **regime fragility** documented above.

## Do-not-cross-use

Do not use USDJPY `M2_S3_*` sizing on EURUSD.

## Deployment

See [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md). Fund live only after restoring ≥2/3 positive sub-period slices (filter or re-validation).
