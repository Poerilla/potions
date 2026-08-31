# NQ Prior-Opposed Resting-Limit: Exclude <=1m Arm-to-Fill Entries

Filter: remove filled campaigns where `minutes_v2b_arm_to_entry_fill <= 1.0` from the resting-limit causal timing table, then recompute the remaining unit/equity/stress audit path.

Important: this is a post-filtered campaign audit, not a full strategy rerun with delayed order placement. A true delay/re-arm rule could alter later same-day sequencing.

| Metric | Full resting-limit baseline | Excluding <=1m fills | Change |
|---|---:|---:|---:|
| Campaigns | 432 | 331 | -101 |
| Units | 2160 | 1655 | -505 |
| Net | $1,330,920.00 | $1,042,682.50 | $-288,237.50 |
| Net retained | 100.00% | 78.34% | 21.66% removed |
| Closed DD, audit path | $-68,110.00 | $-47,731.50 | $20,378.50 improved |
| Intrabar stress DD | $-68,610.00 | $-49,690.80 | $18,919.20 improved |
| Campaign win rate | 65.97% | 66.47% | 0.50 pts |
| Campaign profit factor | 2.339 | 2.444 | 0.105 |
| Net / stress | 19.40 | 20.98 | 1.58 |
| Max open units | 5 | 5 | 0 |

Files:

- `summary.csv`
- `excluded_lte_1m_entries.csv`
- `filtered_unit_trades_source.csv`
- `unit_trades.csv` and `equity_curve.csv` from the filtered stress audit
