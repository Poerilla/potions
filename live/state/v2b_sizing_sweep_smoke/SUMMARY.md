# V2B Scaleout Sizing Sweep

Each row is one per-unit ladder (`tp1_qty / tp2_qty / runner_qty`) for the 
v2b_scaleout plugin driven through the same 1-minute broker-like path used by 
`v2b_strategy_cross_market_replay.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`.

| Rank | Market | Sizing | Entry | TP1 | TP2 | Runner | Sessions | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | MNQ | 1/1/0 (entry 2, no runner) | 2 | 1 | 1 | 0 | 60 | 148 | 74 | $1,124.50 | $-2,905.50 | 0.39 |
| 2 | MNQ | 2/2/0 (entry 4, no runner) | 4 | 2 | 2 | 0 | 60 | 296 | 74 | $2,249.00 | $-5,811.00 | 0.39 |
| 3 | MNQ | 1/1/1 (entry 3, baseline with runner) | 3 | 1 | 1 | 1 | 60 | 222 | 74 | $1,540.00 | $-4,465.50 | 0.34 |
| 4 | MNQ | 2/2/2 (entry 6) | 6 | 2 | 2 | 2 | 60 | 444 | 74 | $3,080.00 | $-8,931.00 | 0.34 |
| 5 | MNQ | 4/2/1 (entry 7) | 7 | 4 | 2 | 1 | 60 | 518 | 74 | $3,235.50 | $-10,305.00 | 0.31 |
| 6 | MNQ | 1/1/3 (entry 5, big runner) | 5 | 1 | 1 | 3 | 60 | 370 | 74 | $2,371.00 | $-7,627.50 | 0.31 |
| 7 | MNQ | 5/2/1 (entry 8) | 8 | 5 | 2 | 1 | 60 | 592 | 74 | $3,521.00 | $-11,782.50 | 0.30 |
| 8 | MNQ | 2/1/2 (entry 5) | 5 | 2 | 1 | 2 | 60 | 370 | 74 | $2,241.00 | $-7,524.00 | 0.30 |
| 9 | MNQ | 3/1/1 (entry 5) | 5 | 3 | 1 | 1 | 60 | 370 | 74 | $2,111.00 | $-7,420.50 | 0.28 |
| 10 | MNQ | 4/1/1 (entry 6) | 6 | 4 | 1 | 1 | 60 | 444 | 74 | $2,396.50 | $-8,898.00 | 0.27 |

## Per-Market Ranking

### MNQ

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/1/0 (entry 2, no runner) | 2 | 1 | 1 | 0 | 148 | $1,124.50 | $-2,905.50 | 0.39 | 43.2% | 1.12 |
| 2/2/0 (entry 4, no runner) | 4 | 2 | 2 | 0 | 296 | $2,249.00 | $-5,811.00 | 0.39 | 43.2% | 1.12 |
| 1/1/1 (entry 3, baseline with runner) | 3 | 1 | 1 | 1 | 222 | $1,540.00 | $-4,465.50 | 0.34 | 41.0% | 1.11 |
| 2/2/2 (entry 6) | 6 | 2 | 2 | 2 | 444 | $3,080.00 | $-8,931.00 | 0.34 | 41.0% | 1.11 |
| 4/2/1 (entry 7) | 7 | 4 | 2 | 1 | 518 | $3,235.50 | $-10,305.00 | 0.31 | 44.2% | 1.10 |
| 1/1/3 (entry 5, big runner) | 5 | 1 | 1 | 3 | 370 | $2,371.00 | $-7,627.50 | 0.31 | 39.2% | 1.10 |
| 5/2/1 (entry 8) | 8 | 5 | 2 | 1 | 592 | $3,521.00 | $-11,782.50 | 0.30 | 44.9% | 1.09 |
| 2/1/2 (entry 5) | 5 | 2 | 1 | 2 | 370 | $2,241.00 | $-7,524.00 | 0.30 | 41.9% | 1.09 |
| 3/1/1 (entry 5) | 5 | 3 | 1 | 1 | 370 | $2,111.00 | $-7,420.50 | 0.28 | 44.6% | 1.09 |
| 4/1/1 (entry 6) | 6 | 4 | 1 | 1 | 444 | $2,396.50 | $-8,898.00 | 0.27 | 45.5% | 1.08 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `states/<slug>/` — broker state, fills, orders, audit for each row.