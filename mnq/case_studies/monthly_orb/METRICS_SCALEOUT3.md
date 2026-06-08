# Monthly ORB restricted — scaleout3 metrics

## Restricted vs scaleout3 (MNQ)

**Stress DD** uses the same daily construction as `yearly_orb_equity_scaling.base_stats`: cumulative **realized** PnL by calendar day from leg exits, minus the sum of **MAE stress** (`MAE_Position_Pts` × $/pt for scaleout3 bundles; path adverse excursion × $/pt for single-leg) for all bundles still open on that day. More negative = more conservative open-heat estimate.

| Metric | Single-leg restricted | Scaleout3 restricted |
|---|---:|---:|
| Trades / bundles | 141 | 139 |
| Net (pts) | 22,019.50 | 52,577.00 |
| Net (USD) | $44,039.00 | $105,154.00 |
| Max MAE price (pts, path) — single-leg | 1,039.25 | — |
| Avg MAE price (pts, path) — single-leg | 194.88 | — |
| Max MAE price (pts) — scaleout sim | — | 1,039.25 |
| Avg MAE price (pts) — scaleout sim | — | 137.04 |
| Worst bundle MAE stress (USD) | $2,078.50 | $4,157.00 |
| Avg bundle MAE stress (USD) | $389.76 | $625.14 |
| Max drawdown — **closed** realized (USD) | $-2,394.00 | $-3,722.75 |
| Max drawdown — **stress / MTM** proxy (USD) | $-4,713.50 | $-6,410.00 |


## Restricted vs scaleout3 (NQ)

**Stress DD** uses the same daily construction as `yearly_orb_equity_scaling.base_stats`: cumulative **realized** PnL by calendar day from leg exits, minus the sum of **MAE stress** (`MAE_Position_Pts` × $/pt for scaleout3 bundles; path adverse excursion × $/pt for single-leg) for all bundles still open on that day. More negative = more conservative open-heat estimate.

| Metric | Single-leg restricted | Scaleout3 restricted |
|---|---:|---:|
| Trades / bundles | 325 | 313 |
| Net (pts) | 27,897.00 | 66,154.62 |
| Net (USD) | $557,940.00 | $1,323,092.50 |
| Max MAE price (pts, path) — single-leg | 1,038.00 | — |
| Avg MAE price (pts, path) — single-leg | 109.37 | — |
| Max MAE price (pts) — scaleout sim | — | 1,038.00 |
| Avg MAE price (pts) — scaleout sim | — | 75.66 |
| Worst bundle MAE stress (USD) | $20,760.00 | $41,520.00 |
| Avg bundle MAE stress (USD) | $2,187.37 | $3,445.77 |
| Max drawdown — **closed** realized (USD) | $-23,955.00 | $-37,277.50 |
| Max drawdown — **stress / MTM** proxy (USD) | $-47,120.00 | $-64,050.00 |


Regenerate charts: `python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py`

Regenerate NQ charts: same with `--nq`.
