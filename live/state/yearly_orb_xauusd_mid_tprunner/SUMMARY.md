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
| 1 | XAUUSD | limit_retest 0/3/3 + mid-close | 0 | 3 | 3 | 6 | limit_retest | mid_close | 50% | 240 | 40 | $954,865.20 | $-200,898.90 | 4.75 |
| 2 | XAUUSD | limit_retest 1/4/4 + mid-close | 1 | 4 | 4 | 9 | limit_retest | mid_close | 50% | 360 | 40 | $1,315,555.20 | $-284,495.70 | 4.62 |
| 3 | XAUUSD | limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $997,266.80 | $-217,529.40 | 4.58 |
| 4 | XAUUSD | limit_retest 2/4/4 + mid-close | 2 | 4 | 4 | 10 | limit_retest | mid_close | 50% | 400 | 40 | $1,357,956.80 | $-301,126.20 | 4.51 |
| 5 | XAUUSD | limit_retest 0/2/4 + mid-close | 0 | 2 | 4 | 6 | limit_retest | mid_close | 50% | 240 | 40 | $1,046,123.40 | $-234,604.20 | 4.46 |
| 6 | XAUUSD | limit_retest 2/3/3 + mid-close | 2 | 3 | 3 | 8 | limit_retest | mid_close | 50% | 320 | 40 | $1,039,668.40 | $-234,159.90 | 4.44 |
| 7 | XAUUSD | limit_retest 1/3/5 + mid-close | 1 | 3 | 5 | 9 | limit_retest | mid_close | 50% | 360 | 40 | $1,406,813.40 | $-318,201.00 | 4.42 |
| 8 | XAUUSD | limit_retest 1/5/3 + mid-close | 1 | 5 | 3 | 9 | limit_retest | mid_close | 50% | 360 | 40 | $1,224,297.00 | $-278,941.20 | 4.39 |
| 9 | XAUUSD | limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $1,088,525.00 | $-251,234.70 | 4.33 |
| 10 | XAUUSD | limit_retest 1/1/1 + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | 120 | 40 | $360,690.00 | $-83,596.80 | 4.31 |
| 11 | XAUUSD | limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | 360 | 40 | $1,082,070.00 | $-250,790.40 | 4.31 |
| 12 | XAUUSD | limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | 320 | 40 | $1,130,926.60 | $-267,865.20 | 4.22 |
| 13 | XAUUSD | limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | 200 | 40 | $770,236.60 | $-184,268.40 | 4.18 |
| 14 | XAUUSD | limit_retest 1/1/5 + mid-close | 1 | 1 | 5 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $1,179,783.20 | $-284,940.00 | 4.14 |
| 15 | XAUUSD | limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | 160 | 40 | $403,091.60 | $-100,227.30 | 4.02 |
| 16 | XAUUSD | limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $601,409.90 | $-163,407.70 | 3.68 |

## Per-Market Ranking

### XAUUSD

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 0/3/3 + mid-close | 0 | 3 | 3 | 6 | limit_retest | mid_close | 50% | $954,865.20 | $-200,898.90 | 4.75 |
| limit_retest 1/4/4 + mid-close | 1 | 4 | 4 | 9 | limit_retest | mid_close | 50% | $1,315,555.20 | $-284,495.70 | 4.62 |
| limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | $997,266.80 | $-217,529.40 | 4.58 |
| limit_retest 2/4/4 + mid-close | 2 | 4 | 4 | 10 | limit_retest | mid_close | 50% | $1,357,956.80 | $-301,126.20 | 4.51 |
| limit_retest 0/2/4 + mid-close | 0 | 2 | 4 | 6 | limit_retest | mid_close | 50% | $1,046,123.40 | $-234,604.20 | 4.46 |
| limit_retest 2/3/3 + mid-close | 2 | 3 | 3 | 8 | limit_retest | mid_close | 50% | $1,039,668.40 | $-234,159.90 | 4.44 |
| limit_retest 1/3/5 + mid-close | 1 | 3 | 5 | 9 | limit_retest | mid_close | 50% | $1,406,813.40 | $-318,201.00 | 4.42 |
| limit_retest 1/5/3 + mid-close | 1 | 5 | 3 | 9 | limit_retest | mid_close | 50% | $1,224,297.00 | $-278,941.20 | 4.39 |
| limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | $1,088,525.00 | $-251,234.70 | 4.33 |
| limit_retest 1/1/1 + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | $360,690.00 | $-83,596.80 | 4.31 |
| limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | $1,082,070.00 | $-250,790.40 | 4.31 |
| limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | $1,130,926.60 | $-267,865.20 | 4.22 |
| limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | $770,236.60 | $-184,268.40 | 4.18 |
| limit_retest 1/1/5 + mid-close | 1 | 1 | 5 | 7 | limit_retest | mid_close | 50% | $1,179,783.20 | $-284,940.00 | 4.14 |
| limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | $403,091.60 | $-100,227.30 | 4.02 |
| limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | $601,409.90 | $-163,407.70 | 3.68 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| XAUUSD | limit_retest 0/3/3 + mid-close | 0/3/3 | $954,865.20 | $-200,898.90 | 4.75 |  |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.