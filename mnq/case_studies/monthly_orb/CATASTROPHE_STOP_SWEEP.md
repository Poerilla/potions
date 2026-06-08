# Monthly ORB Overlap 4H Catastrophe Stop Sweep

Study target: current **breakout-only, 2-active, next-open** overlap-range candidate.

Mechanics tested:

- Long-only stop-breakout package remains 3 contracts: 1 @ TP50, 1 @ TP1, 1 runner @ TP2.
- The catastrophe stop is a live 4-hour stop-touch exit after the entry bar.
- Stop level = combined range high minus the tested fraction of the combined range.
- Same-bar ambiguity uses conservative stop-first ordering.
- Daily-close invalidation remains next-open fill.

## Summary

| Market | Stop depth | Trades | Net USD | Max DD USD | Win rate | PF | Cat exits | Winner impact |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| MNQ | none | 19 | $51,960 | $-5,632 | 57.9% | 5.36 | 0 | baseline |
| MNQ | 40% | 19 | $45,183 | $-4,909 | 52.6% | 5.06 | 7 | clipped 1 baseline winner |
| MNQ | 45% | 19 | $53,069 | $-4,624 | 57.9% | 5.88 | 5 | no baseline winners reduced |
| MNQ | 50% | 19 | $52,667 | $-4,891 | 57.9% | 5.70 | 3 | no baseline winners reduced |
| MNQ | 55% | 19 | $51,892 | $-5,158 | 57.9% | 5.33 | 3 | no baseline winners reduced |
| MNQ | 60% | 19 | $51,118 | $-5,425 | 57.9% | 5.01 | 3 | no baseline winners reduced |
| NQ | none | 46 | $716,052 | $-50,538 | 67.4% | 6.72 | 0 | baseline |
| NQ | 40% | 47 | $640,174 | $-49,086 | 63.8% | 6.23 | 15 | clipped 2 baseline winners |
| NQ | 45% | 46 | $732,093 | $-40,459 | 67.4% | 7.66 | 11 | no baseline winners reduced |
| NQ | 50% | 46 | $728,643 | $-43,128 | 67.4% | 7.47 | 8 | no baseline winners reduced |
| NQ | 55% | 46 | $720,349 | $-45,796 | 67.4% | 6.95 | 7 | no baseline winners reduced |
| NQ | 60% | 46 | $711,949 | $-48,464 | 67.4% | 6.50 | 6 | no baseline winners reduced |

## Read

- **40% is too tight.** It clipped historical baseline winners on both MNQ and NQ.
- **45% is best in-sample.** It improved net, drawdown, profit factor, and did not reduce any baseline winners in this replay.
- **50% is the safer practical candidate.** It still improved net and drawdown without reducing baseline winners, while leaving more room than 45%.
- 55% and 60% preserve winners but give back much of the loss-reduction benefit.

Worst single-loss check:

| Market | Stop depth | Worst single loss |
|---|---:|---:|
| MNQ | none | $-3,411 |
| MNQ | 45% | $-2,895 |
| MNQ | 50% | $-3,217 |
| NQ | none | $-34,095 |
| NQ | 45% | $-28,964 |
| NQ | 50% | $-32,182 |

Conclusion: keep 45% and 50% as live-candidate hardening branches. If avoiding curve-fit risk matters more than maximizing this sample, prefer **50%** first. If the goal is maximum historical efficiency, **45%** is the stronger backtest branch.

## Outputs

- `mnq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/catastrophe_stop_sweep.csv`
- `nq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/catastrophe_stop_sweep.csv`
- Per-depth trade CSVs live beside the overlap causal outputs with names like `*_catstop_50pct.csv`.
