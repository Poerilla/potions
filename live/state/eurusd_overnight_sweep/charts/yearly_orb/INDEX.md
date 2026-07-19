# Broker-Like Replay Detail Charts

These chart packs are generated from the new broker-like replay standard: strategy intents flow through the engine, paper broker, persisted orders, and persisted fills. The older theoretical charts remain in their original case-study folders.

> Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, stop gap-through ON, stop-first same-bar, OCO-collapsed risk.

| Rank | Candidate | Instrument | Net | Stress DD | Net / Stress DD | Charts |
|---:|---|---|---:|---:|---:|---|
| 1 | EURUSD Yearly ORB scaleout3 | EURUSD | $165,865.00 | $-19,965.00 | 8.31 | [eurusd_yearly_orb_scaleout3](eurusd_yearly_orb_scaleout3/INDEX.md) |
| 2 | EURUSD Yearly ORB scaleout3 20% range-close | EURUSD | $124,518.75 | $-47,959.25 | 2.60 | [eurusd_yearly_orb_scaleout3_range_close_20pct](eurusd_yearly_orb_scaleout3_range_close_20pct/INDEX.md) |

## Reference Comparison

- Existing summary chart: [MNQ ATR daily ladder theoretical vs broker-like](../mnq_atr_daily_ladder112221_theoretical_vs_broker_like.png)
- Existing summary chart: [MNQ ATR weekly 2-initial broker-like](../mnq_atr_weekly_2initial_3add_6max_broker_like.png)
