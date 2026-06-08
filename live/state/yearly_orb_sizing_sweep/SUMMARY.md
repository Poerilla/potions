# Yearly ORB Scaleout3 Sizing Sweep

Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for 
`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` 
path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`.

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | NQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 408 | 68 | $1,417,383.00 | $-128,766.00 | 11.01 |
| 2 | NQ | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 544 | 68 | $1,920,829.00 | $-179,992.50 | 10.67 |
| 3 | NQ | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 476 | 68 | $1,731,806.00 | $-169,809.50 | 10.20 |
| 4 | NQ | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 272 | 68 | $1,039,337.00 | $-108,283.00 | 9.60 |
| 5 | NQ | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 544 | 68 | $2,078,674.00 | $-216,566.00 | 9.60 |
| 6 | NQ | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 408 | 68 | $1,542,783.00 | $-162,424.50 | 9.50 |
| 7 | NQ | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 476 | 68 | $1,922,096.00 | $-213,440.00 | 9.01 |
| 8 | MNQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 144 | 24 | $108,526.50 | $-12,850.50 | 8.45 |
| 9 | MNQ | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 192 | 24 | $147,934.12 | $-17,964.88 | 8.23 |
| 10 | NQ | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 204 | 68 | $850,314.00 | $-106,720.00 | 7.97 |
| 11 | NQ | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 408 | 68 | $1,700,628.00 | $-213,440.00 | 7.97 |
| 12 | NQ | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 612 | 68 | $2,550,942.00 | $-320,160.00 | 7.97 |
| 13 | MNQ | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 168 | 24 | $134,406.00 | $-17,007.00 | 7.90 |
| 14 | MNQ | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 96 | 24 | $81,470.25 | $-10,843.00 | 7.51 |
| 15 | MNQ | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 192 | 24 | $162,940.50 | $-21,686.00 | 7.51 |
| 16 | NQ | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 544 | 68 | $2,394,364.00 | $-320,160.00 | 7.48 |
| 17 | MNQ | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 144 | 24 | $120,877.88 | $-16,264.50 | 7.43 |
| 18 | NQ | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 476 | 68 | $1,982,606.00 | $-266,800.00 | 7.43 |
| 19 | NQ | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 340 | 68 | $1,544,050.00 | $-213,440.00 | 7.23 |
| 20 | MNQ | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 168 | 24 | $152,067.38 | $-21,338.00 | 7.13 |
| 21 | NQ | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 476 | 68 | $2,205,341.00 | $-320,160.00 | 6.89 |
| 22 | NQ | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 476 | 68 | $2,172,896.00 | $-320,160.00 | 6.79 |
| 23 | NQ | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 322 | 46 | $1,426,707.00 | $-211,815.00 | 6.74 |
| 24 | MNQ | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 72 | 24 | $67,942.12 | $-10,669.00 | 6.37 |
| 25 | MNQ | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 144 | 24 | $135,884.25 | $-21,338.00 | 6.37 |
| 26 | MNQ | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 216 | 24 | $203,826.38 | $-32,007.00 | 6.37 |
| 27 | MNQ | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 70 | 10 | $128,977.50 | $-21,211.50 | 6.08 |
| 28 | MNQ | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 192 | 24 | $192,953.25 | $-32,007.00 | 6.03 |
| 29 | MNQ | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 168 | 24 | $159,108.75 | $-26,672.50 | 5.97 |
| 30 | MNQ | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 120 | 24 | $125,011.12 | $-21,338.00 | 5.86 |
| 31 | MNQ | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 168 | 24 | $179,425.12 | $-32,007.00 | 5.61 |
| 32 | MNQ | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 168 | 24 | $176,770.12 | $-32,007.00 | 5.52 |
| 33 | NQ | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 138 | 46 | $741,289.25 | $-141,210.00 | 5.25 |
| 34 | MNQ | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 30 | 10 | $66,845.25 | $-14,141.00 | 4.73 |
| 35 | NQ | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 273 | 39 | $1,014,680.50 | $-214,659.50 | 4.73 |
| 36 | MNQ | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 84 | 12 | $92,827.00 | $-21,486.00 | 4.32 |
| 37 | NQ | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 117 | 39 | $516,948.25 | $-141,210.00 | 3.66 |
| 38 | MNQ | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 36 | 12 | $48,136.62 | $-14,141.00 | 3.40 |

## Per-Market Ranking

### MNQ

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $108,526.50 | $-12,850.50 | 8.45 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $147,934.12 | $-17,964.88 | 8.23 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $134,406.00 | $-17,007.00 | 7.90 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $81,470.25 | $-10,843.00 | 7.51 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $162,940.50 | $-21,686.00 | 7.51 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $120,877.88 | $-16,264.50 | 7.43 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $152,067.38 | $-21,338.00 | 7.13 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $67,942.12 | $-10,669.00 | 6.37 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $135,884.25 | $-21,338.00 | 6.37 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $203,826.38 | $-32,007.00 | 6.37 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $128,977.50 | $-21,211.50 | 6.08 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $192,953.25 | $-32,007.00 | 6.03 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $159,108.75 | $-26,672.50 | 5.97 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $125,011.12 | $-21,338.00 | 5.86 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $179,425.12 | $-32,007.00 | 5.61 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $176,770.12 | $-32,007.00 | 5.52 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $66,845.25 | $-14,141.00 | 4.73 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $92,827.00 | $-21,486.00 | 4.32 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $48,136.62 | $-14,141.00 | 3.40 |

### NQ

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $1,417,383.00 | $-128,766.00 | 11.01 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $1,920,829.00 | $-179,992.50 | 10.67 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $1,731,806.00 | $-169,809.50 | 10.20 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $1,039,337.00 | $-108,283.00 | 9.60 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $2,078,674.00 | $-216,566.00 | 9.60 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $1,542,783.00 | $-162,424.50 | 9.50 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $1,922,096.00 | $-213,440.00 | 9.01 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $850,314.00 | $-106,720.00 | 7.97 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $1,700,628.00 | $-213,440.00 | 7.97 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $2,550,942.00 | $-320,160.00 | 7.97 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $2,394,364.00 | $-320,160.00 | 7.48 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $1,982,606.00 | $-266,800.00 | 7.43 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $1,544,050.00 | $-213,440.00 | 7.23 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $2,205,341.00 | $-320,160.00 | 6.89 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $2,172,896.00 | $-320,160.00 | 6.79 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $1,426,707.00 | $-211,815.00 | 6.74 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $741,289.25 | $-141,210.00 | 5.25 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $1,014,680.50 | $-214,659.50 | 4.73 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $516,948.25 | $-141,210.00 | 3.66 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.