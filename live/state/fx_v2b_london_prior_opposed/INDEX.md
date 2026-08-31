# FX / metals / CFD v2b London — prior-opposed S_1_1_3

StrategyPlugin: `v2b_scaleout` + ST+PMC `sl50_tp150_3r_1mfill` gate (`prior_opposed`).

London clock (America/New_York): OR **03:00–03:15**, flatten **11:59**.

| Rank | Symbol | Gate | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NAS100 | prior_opposed | 895 | 322 | $18521 | $-2210 | 8.38 | 30.4 | 1.983 |
| 2 | US30 | prior_opposed | 836 | 300 | $24370 | $-3912 | 6.23 | 35.0 | 1.803 |
| 3 | XAUUSD | prior_opposed | 1929 | 104 | $13259 | $-71770 | 0.18 | 32.9 | 1.100 |
| 4 | XAGUSD | prior_opposed | 1553 | 0 | $0 | $0 | 0.00 | 0.0 | 0.000 |
| 5 | USDJPY | prior_opposed | 1679 | 362 | $-9044 | $-25411 | -0.36 | 26.4 | 0.905 |
| 6 | GBPUSD | prior_opposed | 1435 | 357 | $-30943 | $-46592 | -0.66 | 24.9 | 0.697 |
| 7 | AUDJPY | prior_opposed | 1429 | 308 | $-23425 | $-29301 | -0.80 | 27.5 | 0.741 |
| 8 | EURUSD | prior_opposed | 1354 | 251 | $-23340 | $-24631 | -0.95 | 24.7 | 0.623 |

- Hub: `live/state/fx_v2b_london_prior_opposed`

## Live demos (2026-08-11)

US30 only — **¼ size** (`S_1_0_0`, `size_mult=0.25`) until live ST parity + concentration clarity:

| Mode | Run dir | CLI | ST feed |
|------|---------|-----|---------|
| paper | `live/demo/us30_london_prior_opposed_paper/` | `demo-us30-london-prior-opposed-paper` | `…_3r_paper` |
| OANDA practice | `live/demo/us30_london_prior_opposed_oanda/` | `demo-us30-london-prior-opposed-oanda` | `…_3r_oanda` |

Artifacts: `gate_audit.csv` (arm/disarm / prior ST / OCO / fill / skip), `st_events.json`, `state/fills.csv`.

