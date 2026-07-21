# FX Monday OR breakout — broker progress log

2026-07-20 — StrategyPlugin `monday_or_breakout` battle test across fx/raw pairs.

## Steps completed
1. Registered plugin in `live/strategies/monday_or_breakout.py` + registry.
2. Driver `live/fx_monday_or_breakout_broker.py` — 15m bars, Engine + PaperBroker, 1-tick slip, $1.50/unit.
3. Config: 3 lots, DD30 drop2 / DD50 cut1, TP=2R, shifted primary parallel, HTF both-opposed skip.
4. Replayed: EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD.
5. Audited Net / Stress DD / Net/Stress; JPY pairs ≈USD @ 110.
6. Charted 100 USDJPY winners + 100 losers → `charts_usdjpy/{winners,losers}/`.
7. Updated STRATEGY_TRACKER Forex section, MONDAY_ORB_FAMILY.md, RESEARCH.md, live/CHANGE_LOG.md.

## Headline (≈USD N/S)
USDJPY 4.27 · GBPUSD 1.87 · AUDJPY 1.07 · XAUUSD 1.04 · EURUSD 0.83 · XAGUSD −1.00

## Viability note
EURUSD broker CE below promoted ST+PMC (1.49). Cross-pair USDJPY/GBPUSD carry the sleeve.
Research pandas EURUSD CE was 2.21 (closed DD) — compressed by slip + next-open entry under broker.

## Artifacts
- SUMMARY.md / results.csv / states/ / audits/ / charts_usdjpy/
- Family research: ../eurusd_monday_or_breakout_15m/RESEARCH.md
- Sizing sweep Phase 1: ../monday_or_sizing_sweep/INDEX.md
  (EURUSD M1_S2_R2 CE 3.28; USDJPY M3_S3_R2 CE 13.37 — broker confirm pending)
