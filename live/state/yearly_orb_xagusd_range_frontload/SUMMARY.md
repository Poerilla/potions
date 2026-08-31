# Yearly ORB Scaleout3 Sizing Sweep

Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for 
`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` 
path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, per-market fees 
(futures/metals $1.50; AUDJPY ¥7), stop gap-through ON, stop-first same-bar, 
OCO-collapsed risk projection.

Causal market exits: range-close / mid-close / year-change flatten with 
`live_after_ts=decision_bar.ts` so fills occur on the **next daily open**, 
not the same completed bar's open (lookahead fix). 
`inside_swing_take` disables range/mid market flatten and trails the 
protective stop to the latest confirmed inside-range swing.

Ranking is by `Net / Stress DD` (currency-invariant). AUDJPY ~USD uses ÷110.

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | XAGUSD | limit_retest 6/2/1 | 6 | 2 | 1 | 9 | limit_retest | range_close | — | 801 | 89 | $85,744.00 | $-62,650.50 | 1.37 |
| 2 | XAGUSD | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | 712 | 89 | $75,641.75 | $-56,814.50 | 1.33 |
| 3 | XAGUSD | limit_retest 6/1/1 | 6 | 1 | 1 | 8 | limit_retest | range_close | — | 712 | 89 | $73,666.50 | $-56,814.50 | 1.30 |
| 4 | XAGUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 623 | 89 | $65,539.50 | $-50,978.50 | 1.29 |
| 5 | XAGUSD | limit_retest 4/3/1 | 4 | 3 | 1 | 8 | limit_retest | range_close | — | 712 | 89 | $77,617.00 | $-61,034.50 | 1.27 |
| 6 | XAGUSD | limit_retest 5/1/1 | 5 | 1 | 1 | 7 | limit_retest | range_close | — | 623 | 89 | $63,564.25 | $-50,978.50 | 1.25 |
| 7 | XAGUSD | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 534 | 89 | $53,462.00 | $-45,142.50 | 1.18 |
| 8 | XAGUSD | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | 534 | 89 | $55,437.25 | $-48,307.50 | 1.15 |
| 9 | XAGUSD | limit_retest 3/3/1 | 3 | 3 | 1 | 7 | limit_retest | range_close | — | 623 | 89 | $67,514.75 | $-60,298.50 | 1.12 |
| 10 | XAGUSD | limit_retest 3/1/1 | 3 | 1 | 1 | 5 | limit_retest | range_close | — | 445 | 89 | $43,359.75 | $-39,306.50 | 1.10 |
| 11 | XAGUSD | limit_retest 5/2/2 | 5 | 2 | 2 | 9 | limit_retest | range_close | — | 801 | 89 | $76,617.25 | $-72,777.00 | 1.05 |
| 12 | XAGUSD | limit_retest 2/2/1 | 2 | 2 | 1 | 5 | limit_retest | range_close | — | 445 | 89 | $45,335.00 | $-47,571.50 | 0.95 |
| 13 | XAGUSD | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | 712 | 89 | $66,515.00 | $-71,161.00 | 0.93 |
| 14 | XAGUSD | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | 356 | 89 | $33,257.50 | $-35,580.50 | 0.93 |
| 15 | XAGUSD | limit_retest 1/1/1 | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 267 | 89 | $23,155.25 | $-34,844.50 | 0.66 |
| 16 | XAGUSD | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | 623 | 89 | $49,261.25 | $-103,061.50 | 0.48 |
| 17 | XAGUSD | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | 623 | 89 | $38,159.25 | $-113,188.00 | 0.34 |

## Per-Market Ranking

### XAGUSD

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 6/2/1 | 6 | 2 | 1 | 9 | limit_retest | range_close | — | $85,744.00 | $-62,650.50 | 1.37 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | $75,641.75 | $-56,814.50 | 1.33 |
| limit_retest 6/1/1 | 6 | 1 | 1 | 8 | limit_retest | range_close | — | $73,666.50 | $-56,814.50 | 1.30 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $65,539.50 | $-50,978.50 | 1.29 |
| limit_retest 4/3/1 | 4 | 3 | 1 | 8 | limit_retest | range_close | — | $77,617.00 | $-61,034.50 | 1.27 |
| limit_retest 5/1/1 | 5 | 1 | 1 | 7 | limit_retest | range_close | — | $63,564.25 | $-50,978.50 | 1.25 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $53,462.00 | $-45,142.50 | 1.18 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | $55,437.25 | $-48,307.50 | 1.15 |
| limit_retest 3/3/1 | 3 | 3 | 1 | 7 | limit_retest | range_close | — | $67,514.75 | $-60,298.50 | 1.12 |
| limit_retest 3/1/1 | 3 | 1 | 1 | 5 | limit_retest | range_close | — | $43,359.75 | $-39,306.50 | 1.10 |
| limit_retest 5/2/2 | 5 | 2 | 2 | 9 | limit_retest | range_close | — | $76,617.25 | $-72,777.00 | 1.05 |
| limit_retest 2/2/1 | 2 | 2 | 1 | 5 | limit_retest | range_close | — | $45,335.00 | $-47,571.50 | 0.95 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | $66,515.00 | $-71,161.00 | 0.93 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | $33,257.50 | $-35,580.50 | 0.93 |
| limit_retest 1/1/1 | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $23,155.25 | $-34,844.50 | 0.66 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | $49,261.25 | $-103,061.50 | 0.48 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | $38,159.25 | $-113,188.00 | 0.34 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| XAGUSD | limit_retest 6/2/1 | 6/2/1 | $85,744.00 | $-62,650.50 | 1.37 | +0.70 N/S |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.