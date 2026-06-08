# V2B Scaleout Sizing Sweep

Each row is one per-unit ladder (`tp1_qty / tp2_qty / runner_qty`) for the 
v2b_scaleout plugin driven through the same 1-minute broker-like path used by 
`v2b_strategy_cross_market_replay.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`.

| Rank | Market | Sizing | Entry | TP1 | TP2 | Runner | Sessions | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | 1/0/0 TP1-only (entry 1) | 1 | 1 | 0 | 0 | 1164 | 1303 | 1303 | $121,160.50 | $-32,475.00 | 3.73 |
| 2 | MNQ | 1/0/0 TP1-only (entry 1) | 1 | 1 | 0 | 0 | 1164 | 1306 | 1306 | $10,084.50 | $-3,109.00 | 3.24 |

## Per-Market Ranking

### MNQ

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/0/0 TP1-only (entry 1) | 1 | 1 | 0 | 0 | 1306 | $10,084.50 | $-3,109.00 | 3.24 | 54.5% | 1.11 |

### NQ

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/0/0 TP1-only (entry 1) | 1 | 1 | 0 | 0 | 1303 | $121,160.50 | $-32,475.00 | 3.73 | 54.6% | 1.14 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `states/<slug>/` — broker state, fills, orders, audit for each row.