# Broker-Like Replay Detail Charts

These chart packs are generated from the new broker-like replay standard: strategy intents flow through the engine, paper broker, persisted orders, and persisted fills. The older theoretical charts remain in their original case-study folders.

> Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, stop gap-through ON, stop-first same-bar, OCO-collapsed risk.

| Rank | Candidate | Instrument | Net | Stress DD | Net / Stress DD | Charts |
|---:|---|---|---:|---:|---:|---|
| 1 | EURUSD Monthly ORB restricted scaleout3 | EURUSD | $21,841.25 | $-48,307.50 | 0.45 | [eurusd_monthly_orb_restricted_scaleout3](eurusd_monthly_orb_restricted_scaleout3/INDEX.md) |
| 2 | EURUSD Monthly ORB restricted scaleout3 boundary-stop entry | EURUSD | $-153,062.50 | $-164,402.50 | -0.93 | [eurusd_monthly_orb_restricted_scaleout3_boundary_stop](eurusd_monthly_orb_restricted_scaleout3_boundary_stop/INDEX.md) |

## Reference Comparison

- Existing summary chart: [MNQ ATR daily ladder theoretical vs broker-like](../mnq_atr_daily_ladder112221_theoretical_vs_broker_like.png)
- Existing summary chart: [MNQ ATR weekly 2-initial broker-like](../mnq_atr_weekly_2initial_3add_6max_broker_like.png)
