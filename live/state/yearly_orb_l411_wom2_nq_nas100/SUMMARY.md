# Yearly ORB Scaleout3 Sizing Sweep

Focused broker-like pack: **L_4_1_1** baseline vs **allow_weeks_of_month=[2]** on
NQ futures and NAS100 CFD. Plugin gate arms only in week-of-month 2 and cancels
resting entries outside that window (stricter than post-filtering fills by
`entry_ts` week).

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
| 1 | NAS100 | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 210 | 35 | $34,334.50 | $-5,548.40 | 6.19 |
| 2 | NQ | limit_retest 4/1/1 WoM2 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 90 | 15 | $324,525.00 | $-63,420.00 | 5.12 |
| 3 | NQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 408 | 68 | $764,503.00 | $-159,309.00 | 4.80 |
| 4 | NAS100 | limit_retest 4/1/1 WoM2 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 42 | 7 | $10,248.10 | $-3,464.60 | 2.96 |

## Per-Market Ranking

### NAS100

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $34,334.50 | $-5,548.40 | 6.19 |
| limit_retest 4/1/1 WoM2 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $10,248.10 | $-3,464.60 | 2.96 |

### NQ

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 4/1/1 WoM2 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $324,525.00 | $-63,420.00 | 5.12 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $764,503.00 | $-159,309.00 | 4.80 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| NAS100 | limit_retest 4/1/1 | 4/1/1 | $34,334.50 | $-5,548.40 | 6.19 |  |
| NQ | limit_retest 4/1/1 WoM2 | 4/1/1 | $324,525.00 | $-63,420.00 | 5.12 |  |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.