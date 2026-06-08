# V2B Scaleout Sizing Sweep

Each row is one per-unit ladder (`tp1_qty / tp2_qty / runner_qty`) for the 
v2b_scaleout plugin driven through the same 1-minute broker-like path used by 
`v2b_strategy_cross_market_replay.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`.

| Rank | Market | Sizing | Entry | TP1 | TP2 | Runner | Sessions | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 1164 | 2761 | 1385 | $326,203.50 | $-45,995.00 | 7.09 |
| 2 | MNQ | 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 1164 | 2756 | 1383 | $27,869.00 | $-4,698.50 | 5.93 |
| 3 | MYM | 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 1160 | 2735 | 1374 | $-1,511.00 | $-9,482.62 | -0.16 |

## Per-Market Ranking

### MNQ

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 2756 | $27,869.00 | $-4,698.50 | 5.93 | 43.9% | 1.15 |

### MYM

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 2735 | $-1,511.00 | $-9,482.62 | -0.16 | 43.1% | 0.98 |

### NQ

| Sizing | Entry | TP1 | TP2 | Runner | Units | Net | Stress DD | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/0/1 (entry 2, TP1 + runner) | 2 | 1 | 0 | 1 | 2761 | $326,203.50 | $-45,995.00 | 7.09 | 44.1% | 1.18 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `states/<slug>/` — broker state, fills, orders, audit for each row.