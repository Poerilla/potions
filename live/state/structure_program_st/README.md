# Structure-program ST studies

Narrative of how we got here: [RESEARCH_PATH.md](RESEARCH_PATH.md).

## Analytic

- [core](core/SUMMARY.md) — limit at broken 1m ST stop; SL at structure key
- [structure_sl](structure_sl/SUMMARY.md) — ST-break signal; limit at structure key; risk 50pts
- [structure_sl_scale](structure_sl_scale/SUMMARY.md) — structure limit; risk 8pts; 4ct scale 2@1R → BE, runners 2@3R
- [structure_sl_scale_run](structure_sl_scale_run/SUMMARY.md) — 15ct batches 5@+22/+50/+200; fav ST→BE; extension hits
- [GATE.md](structure_sl_scale_run/GATE.md) — fav ST-flip forward hold reaches 100/200 often enough
- Sweep / cross-market: [SWEEP.md](SWEEP.md), [NET_STRESS_RANK.csv](NET_STRESS_RANK.csv)
- **Bias-level charts** (no trades): [bias_level_charts/](bias_level_charts/) — 15m bias episodes + 1h structure confluence on week 15m candles (~100 PNGs)
- **Bias week packs** (150 each, paired ids): [bias_weeks_1h/](bias_weeks_1h/) (1h, ~1mo windows) · [bias_weeks_15m/](bias_weeks_15m/) (15m week)
- **4h structure bias charts**: [bias_4h_3mo/](bias_4h_3mo/) — 4h StructureProgramEngine; **1 chart/calendar quarter** + 4h ST 14×3
- **Gap fade** (FAIL): [gap_fade/](gap_fade/) — overnight gap vs bias H/L (−$2.4M PF 0.20)
- **Bias-OR OCO 1/1/2/1**: [bias_or_oco/](bias_or_oco/) — bias candle as OR; 09:30 arm; trade-through only; 2@EOD + 1×20R runner (stackable); 2 attempts

## Broker-like (StrategyPlugin + PaperBroker)

- split15 r12 (failed gate): `../structure_program_st_broker/`, `../structure_program_st_broker_adverse/`, `../structure_program_st_broker_aftern10/`, `../structure_program_st_broker_noflip/`
- **scale_run r8** (current): `../structure_program_st_broker_scale_run/` — DSR TRL-2026-00079
