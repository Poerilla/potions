# EURUSD hourly ST day-bias DCA — broker stress

Engine + PaperBroker. **1h signals / 1m fills.** Unit = 0.5 lot (PV $50k), fee $0.75,
1-tick slip + FX half-spread. Window matches research (default 2015 → 2026-03).

Gate vs promoted sleeve: net ≥ $24k and Net/Stress ≥ 1.49.

| Strategy | f | Period | Net | Stress DD | Net/Stress | Units | WR | Max open | Promote? |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| eurusd_st_daybias_f30_week | 30% | week | $-590 | $-9,780 | -0.06 | 672 | 21.6% | 3 | no |
| eurusd_st_daybias_f30_month | 30% | month | $-11,688 | $-19,398 | -0.60 | 671 | 14.2% | 4 | no |
| eurusd_st_daybias_f40_week | 40% | week | $-8,468 | $-13,356 | -0.63 | 673 | 19.9% | 3 | no |
| eurusd_st_daybias_f40_month | 40% | month | $-19,151 | $-26,339 | -0.73 | 673 | 14.1% | 4 | no |
| eurusd_st_daybias_f50_week | 50% | week | $-20,032 | $-24,787 | -0.81 | 675 | 22.5% | 4 | no |

**Verdict: none promote.** Best cell (f30 week) is ≈breakeven on net and negative Net/Stress.
Pandas research was optimistic — see [`RESEARCH.md`](RESEARCH.md).

Promoted FX sleeve unchanged: [`../eurusd_forex_intraday_baseline/`](../eurusd_forex_intraday_baseline/).

Research (pandas): `../eurusd_hourly_st_daybias_dca/SUMMARY.md`  
States / audits under this folder.
