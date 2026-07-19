# EURUSD hourly ST day-bias DCA — broker stress

Engine + PaperBroker. **1h signals / 1m fills.** Unit = 0.5 lot (PV $50k), fee $0.75,
1-tick slip + FX half-spread. Window matches research (default 2015 → 2026-03).

Gate vs promoted sleeve: net ≥ $24k and Net/Stress ≥ 1.49.

| Strategy | f | Period | TP | Net | Stress DD | Net/Stress | Units | WR | Max open | Promote? |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| eurusd_st_daybias_f30_week_tp_4atr | 30% | week | 4×ATR | $-1,464 | $-6,723 | -0.22 | 672 | 27.4% | 3 | no |
| eurusd_st_daybias_f30_week_tp_3atr | 30% | week | 3×ATR | $-3,317 | $-6,260 | -0.53 | 672 | 31.2% | 2 | no |

Research (pandas) pack: `../eurusd_hourly_st_daybias_dca/SUMMARY.md`
States / audits under this folder.
