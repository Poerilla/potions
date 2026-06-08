# Yearly ORB Bias Filter On Adaptive v2b-Only Scaleout

Study: filter the current v2b-only adaptive 50/150 scaleout book using prior-day yearly ORB context.

Primary rule:

- Jan-Mar defines the yearly opening range.
- Trade only after the yearly range is complete.
- The prior trading day must have traded outside the yearly range.
- If prior day traded above yearly OR high, allow only Long v2b scaleout legs.
- If prior day traded below yearly OR low, allow only Short v2b scaleout legs.
- If prior day traded both sides of the yearly OR, skip as ambiguous.

This is a filter over already-resimulated v2b-only scaleout legs. It does not change entries, exits, fills, or scaleout mechanics.

## Results

| Market | Variant | Legs | Days | Net | Trade DD | Daily DD | Win Rate | PF | Avg Trade |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Baseline v2b-only adaptive scaleout | 1,430 | 958 | $35,847 | -$5,190 | -$4,958 | 55.0% | 1.19 | $25.07 |
| MNQ | Prior-day traded outside, aligned | 465 | 465 | $12,672 | -$4,362 | -$4,362 | 55.7% | 1.24 | $27.25 |
| MNQ | Prior-day close outside, aligned | 449 | 449 | $11,892 | -$4,811 | -$4,811 | 55.9% | 1.23 | $26.49 |
| MNQ | Prior-day traded outside, no direction filter | 911 | 616 | $22,590 | -$5,069 | -$4,958 | 55.3% | 1.20 | $24.80 |
| NQ | Baseline v2b-only adaptive scaleout | 4,739 | 3,149 | $414,773 | -$100,010 | -$99,274 | 51.9% | 1.13 | $87.52 |
| NQ | Prior-day traded outside, aligned | 1,358 | 1,358 | $118,911 | -$40,966 | -$40,966 | 51.8% | 1.13 | $87.56 |
| NQ | Prior-day close outside, aligned | 1,307 | 1,307 | $124,399 | -$45,243 | -$45,243 | 52.0% | 1.14 | $95.18 |
| NQ | Prior-day traded outside, no direction filter | 2,651 | 1,784 | $274,827 | -$53,544 | -$52,808 | 52.1% | 1.15 | $103.67 |

## Read

The directional yearly ORB filter is not an upgrade to the current v2b-only candidate.

It does reduce drawdown, especially on NQ, but it cuts too much of the book and does not materially improve win rate or profit factor. The NQ confirmation is especially useful here: the aligned version keeps only 1,358 of 4,739 legs and preserves about 29% of net profit while keeping about 41% of trade drawdown.

The more interesting diagnostic is the no-direction filter: simply requiring the prior day to have traded outside the yearly ORB keeps more of the edge and has better NQ efficiency than the aligned version. Even there, it still does not clearly beat the simple baseline because it gives up too much total PnL for the drawdown reduction.

Conclusion: keep the yearly ORB as context, but do not add this directional filter to the adaptive v2b-only scaleout winner.

## Files

- Script: `scripts/filter_v2b_scaleout_yearly_orb_bias.py`
- MNQ primary filtered trades: `mnq_adaptive_v2b_scaleout_yearly_orb_bias.csv`
- NQ primary filtered trades: `nq_adaptive_v2b_scaleout_yearly_orb_bias.csv`
- MNQ tagged source: `mnq_adaptive_v2b_scaleout_yearly_orb_tagged.csv`
- NQ tagged source: `nq_adaptive_v2b_scaleout_yearly_orb_tagged.csv`
- MNQ summary: `mnq_adaptive_v2b_scaleout_yearly_orb_bias_summary.csv`
- NQ summary: `nq_adaptive_v2b_scaleout_yearly_orb_bias_summary.csv`
