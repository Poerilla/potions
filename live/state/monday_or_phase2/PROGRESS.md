# Monday OR Phase 2 — progress log

## 2026-07-28 — USDJPY Aug+Sep locked core

Added `skip_entry_months=[8,9]` to USDJPY `M2_S3_R1` / `M2_S3_R2` tags + `PAIR_TUNEUPS`.
Promoted broker metrics to `*_tuneup` (N/S **10.60 / 10.62**). Docs updated.

## 2026-07-28 — USDJPY Aug+Sep skip (StrategyPlugin)

Broker-tested `skip_entry_months=[8,9]` on top of prior USDJPY cores:

- R1: N/S **8.78 → 10.60**, net **+$50.5k**, MTM DD unchanged  
- R2: N/S **8.81 → 10.62**, net **+$51.0k**, MTM DD unchanged  

## 2026-07-28 — season/DOW screen on other pairs + gold month counts

Screened month/DOW sit-outs on USDJPY (tuneup), EUR/GBP/AUD (Phase 1), and counted
trades/month on **XAU core** (sitout+100 + skip Jul/Sep/Dec).

- Gold Jul/Sep/Dec = 0 trades; active months ~10–23 trades/year (Jan ~23).
- Jul/Sep/Dec transplant to FX: **hurts USDJPY/AUDJPY**; near-noise on EUR/GBP.
- USDJPY soft block candidate: **Aug+Sep** → later broker-confirmed and locked.

See `season_scan/SUMMARY.md`.

## 2026-07-28 — XAUUSD core: sitout +100 + skip Jul/Sep/Dec

**Action:** Locked calendar blackout into `monday_or_breakout` (`skip_entry_months`)
and `FOOTNOTE_TAGS` / `PAIR_TUNEUPS` for `XAUUSD` `M2_S2_R3`. Ran full
StrategyPlugin Engine + PaperBroker replay
(`monday_or_tuneup_broker --force --cells XAUUSD:M2_S2_R3`).

**Broker result (core):**

| | Net ≈$ | MTM DD ≈$ | N/S |
|---|---:|---:|---:|
| Phase 1 | +437,940 | −230,359 | 1.90 |
| Prior sitout-only | +510,243 | −214,892 | 2.37 |
| **New core** | **+580,139** | **−172,265** | **3.37** |

## 2026-07-28 — earlier same day

- USDJPY / EUR / GBP tune-up broker audits; EUR/GBP skip-after-W rejected.
- XAU sitout +100 first broker lock (N/S 2.37).
- Fill-proxy cluster/skip multi + Jul/Sep/Dec quick study → prompted season lock.
- Phantom-exit fade / US30 work earlier in session (separate track).
