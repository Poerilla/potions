# SPEC — USDJPY Monday OR `M2_S3_R1`

**Status:** Phase 2 default candidate · eligible for limited live / funded paper under caps.  
**Alternate:** `M2_S3_R2` (max 3/week) — near-tie N/S 8.19, slightly higher dollars.  
**Plugin:** `monday_or_breakout` · `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Same Monday OR framework as EURUSD: Mon H/L → Tue–Fri 15m close breakout → SL 1R / TP 2R → DD ladder → shifted primary at opposite Mon extreme after flat@50% → HTF both-opposed skip. USDJPY uses a **runner-heavier main** (cut only 1 at 30%, hold 2 to 50%) and a **heavier shifted sidecar** (4 units), with a tighter weekly cap (max 2 primaries).

## Parameter tags

| Tag | Meaning |
|---|---|
| `M2` | Main 3 = 1@30% DD, 2@50% DD |
| `S3` | Shifted 4 = 2@30% DD, 2@50% DD |
| `R1` | Max **2** primary trades/week (primary) |
| `R2` | Max **3**/week (alternate `M2_S3_R2`) |
| sitout | R1: rest-of-week after +3 yen pts |
| season | Skip **Aug + Sep** entries (both tags) |

## Key metrics (StrategyPlugin broker)

| Metric | `M2_S3_R1` Phase1 | +sitout3 | **+sitout3 + skip Aug/Sep (core)** | `M2_S3_R2` Phase1 | +skip1@2W | **+skip1@2W + skip Aug/Sep (core)** |
|---|---:|---:|---:|---:|---:|---:|
| ≈USD Net | +$218.9k | +$243.5k | **+$294.0k** | +$227.6k | +$249.3k | **+$300.3k** |
| MTM / Stress DD | −$26.7k | −$27.7k | −$27.7k | −$27.8k | −$28.3k | −$28.3k |
| **Net/Stress** | **8.20** | **8.78** | **10.60** | **8.19** | **8.81** | **10.62** |

Core knobs: R1 `week_sitout_after_pts=3` + `skip_entry_months=[8,9]`;  
R2 `skip_after_win_streak=2` + `skip_entry_months=[8,9]`.  
Artifacts: `tuneup_broker/states/usdjpy_m2_s3_r*_tuneup/`.

Pandas pick `M3_S3_R2` is broker #3 (7.54) — research-only.

## Behaviour summary

USDJPY rewards thrust + stop-run / opposite-extreme follow-through: keep more size deeper into the DD ladder on the main leg and size up the shifted sidecar. EURUSD’s light-sidecar recipe ranks near the bottom on this pair.

## Robustness (Phase 2)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 3/3 (pre-2020, 2020–22, 2023+) |
| Clustering | OK — top week ~6%; top 5% weeks ~30% of gross positive |
| Lighter sidecar `M2_S2_R1` | N/S 5.66 — still strong; heavy sidecar amplifies |
| DD sensitivity | **PASS** — 25/45 N/S 6.58 (−20%); 35/55 N/S 8.28 |

## Capacity sketch

Initial **3–5M** notional equivalent. USDJPY is among the deepest FX markets; at this sleeve size, liquidity is not the binding constraint — operational DD and live tracking are.

## Do-not-cross-use

Do not deploy EURUSD `M1_S2_R2` sizing on USDJPY.

## Deployment

See [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md). Scale +1.5× after 6–12 months within BT N/S and DD bands.
