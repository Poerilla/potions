# ATR Supertrend DCA Sizing Sweep

Each row is one ATR Supertrend DCA sizing combination run through the same broker-like 
`Engine` + `PaperBroker` path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`. Net DD is intrabar stress mark-to-market.

| Rank | Market | Sizing | Init | Add | Max | Intv (wks) | Sched | Guard | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | NQ | Daily ladder 1/1/2/2/2/1 / 10-max / interval=2 | 1 | 1 | 10 | 2 | ladder112221 | yes | 402 | 149 | $1,572,142.00 | $-255,950.00 | 6.14 |
| 2 | MNQ | Daily ladder 1/1/2/2/2/1 / 10-max / interval=2 | 1 | 1 | 10 | 2 | ladder112221 | yes | 162 | 52 | $146,875.00 | $-25,610.00 | 5.74 |
| 3 | NQ | Daily 3-initial / 1-add / 10-max / interval=2 | 3 | 1 | 10 | 2 | fixed | yes | 623 | 149 | $1,717,280.50 | $-309,068.50 | 5.56 |
| 4 | MNQ | Daily 3-initial / 1-add / 10-max / interval=2 | 3 | 1 | 10 | 2 | fixed | yes | 233 | 52 | $159,819.00 | $-29,350.50 | 5.45 |
| 5 | NQ | Daily 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | fixed | yes | 492 | 149 | $1,407,832.00 | $-299,903.00 | 4.69 |
| 6 | NQ | Daily 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | fixed | yes | 509 | 149 | $1,456,261.50 | $-312,729.50 | 4.66 |
| 7 | MNQ | Daily 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | fixed | yes | 174 | 52 | $132,988.00 | $-28,743.00 | 4.63 |
| 8 | MNQ | Daily 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | fixed | yes | 177 | 52 | $137,281.50 | $-30,036.50 | 4.57 |
| 9 | NQ | Weekly 2/3/6/intv=2 (no entry guard) | 2 | 3 | 6 | 2 | fixed | no | 66 | 11 | $1,770,601.00 | $-476,134.00 | 3.72 |
| 10 | NQ | Weekly 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | fixed | yes | 127 | 38 | $1,443,304.50 | $-428,513.00 | 3.37 |
| 11 | NQ | Weekly 2-initial / 2-add / 5-max / interval=2 | 2 | 2 | 5 | 2 | fixed | yes | 114 | 38 | $1,191,889.00 | $-363,906.50 | 3.28 |
| 12 | NQ | Weekly 2-initial / 3-add / 8-max / interval=2 | 2 | 3 | 8 | 2 | fixed | yes | 151 | 38 | $1,857,848.50 | $-577,376.00 | 3.22 |
| 13 | NQ | Weekly 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | fixed | yes | 126 | 38 | $1,399,161.00 | $-438,338.00 | 3.19 |
| 14 | NQ | Weekly 3-initial / 2-add / 8-max / interval=2 | 3 | 2 | 8 | 2 | fixed | yes | 175 | 38 | $1,827,402.50 | $-608,600.50 | 3.00 |
| 15 | NQ | Weekly 1-initial / 2-add / 6-max / interval=2 | 1 | 2 | 6 | 2 | fixed | yes | 99 | 38 | $1,345,616.50 | $-448,338.50 | 3.00 |
| 16 | NQ | Custom ladder 1/2/2/2/1 / 6-max / interval=2 | 1 | 1 | 6 | 2 | ladder112221 | yes | 99 | 38 | $1,345,616.50 | $-448,338.50 | 3.00 |
| 17 | NQ | Weekly 1-initial / 1-add / 6-max / interval=1 | 1 | 1 | 6 | 1 | fixed | yes | 104 | 38 | $1,361,639.00 | $-459,423.50 | 2.96 |
| 18 | MNQ | Weekly 2/3/6/intv=2 (no entry guard) | 2 | 3 | 6 | 2 | fixed | no | 30 | 5 | $139,316.50 | $-47,572.00 | 2.93 |
| 19 | NQ | Weekly 3-initial / 1-add / 6-max / interval=2 | 3 | 1 | 6 | 2 | fixed | yes | 150 | 38 | $1,368,715.00 | $-474,725.50 | 2.88 |
| 20 | MNQ | Weekly 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | fixed | yes | 54 | 17 | $119,295.00 | $-42,836.50 | 2.78 |
| 21 | MNQ | Weekly 2-initial / 2-add / 5-max / interval=2 | 2 | 2 | 5 | 2 | fixed | yes | 49 | 17 | $98,310.00 | $-36,377.50 | 2.70 |
| 22 | MNQ | Weekly 2-initial / 3-add / 8-max / interval=2 | 2 | 3 | 8 | 2 | fixed | yes | 64 | 17 | $153,169.00 | $-57,713.50 | 2.65 |
| 23 | MNQ | Weekly 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | fixed | yes | 54 | 17 | $115,247.00 | $-43,816.00 | 2.63 |
| 24 | NQ | Weekly 2-initial / 2-add / 6-max / interval=4 | 2 | 2 | 6 | 4 | fixed | yes | 120 | 38 | $1,241,290.00 | $-486,618.00 | 2.55 |
| 25 | MNQ | Weekly 3-initial / 2-add / 8-max / interval=2 | 3 | 2 | 8 | 2 | fixed | yes | 76 | 17 | $148,817.50 | $-60,846.50 | 2.45 |
| 26 | MNQ | Weekly 1-initial / 2-add / 6-max / interval=2 | 1 | 2 | 6 | 2 | fixed | yes | 42 | 17 | $109,414.50 | $-44,825.50 | 2.44 |
| 27 | MNQ | Custom ladder 1/2/2/2/1 / 6-max / interval=2 | 1 | 1 | 6 | 2 | ladder112221 | yes | 42 | 17 | $109,414.50 | $-44,825.50 | 2.44 |
| 28 | MNQ | Weekly 1-initial / 1-add / 6-max / interval=1 | 1 | 1 | 6 | 1 | fixed | yes | 43 | 17 | $111,511.00 | $-45,856.00 | 2.43 |
| 29 | MNQ | Weekly 3-initial / 1-add / 6-max / interval=2 | 3 | 1 | 6 | 2 | fixed | yes | 66 | 17 | $110,895.50 | $-47,523.50 | 2.33 |
| 30 | MNQ | Weekly 2-initial / 2-add / 6-max / interval=4 | 2 | 2 | 6 | 4 | fixed | yes | 54 | 17 | $97,252.00 | $-48,640.00 | 2.00 |

## Per-Market Net / Stress

### MNQ

| Sizing | Init | Add | Max | Intv | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---:|---:|---:|
| Daily ladder 1/1/2/2/2/1 / 10-max / interval=2 | 1 | 1 | 10 | 2 | $146,875.00 | $-25,610.00 | 5.74 |
| Daily 3-initial / 1-add / 10-max / interval=2 | 3 | 1 | 10 | 2 | $159,819.00 | $-29,350.50 | 5.45 |
| Daily 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | $132,988.00 | $-28,743.00 | 4.63 |
| Daily 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | $137,281.50 | $-30,036.50 | 4.57 |
| Weekly 2/3/6/intv=2 (no entry guard) | 2 | 3 | 6 | 2 | $139,316.50 | $-47,572.00 | 2.93 |
| Weekly 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | $119,295.00 | $-42,836.50 | 2.78 |
| Weekly 2-initial / 2-add / 5-max / interval=2 | 2 | 2 | 5 | 2 | $98,310.00 | $-36,377.50 | 2.70 |
| Weekly 2-initial / 3-add / 8-max / interval=2 | 2 | 3 | 8 | 2 | $153,169.00 | $-57,713.50 | 2.65 |
| Weekly 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | $115,247.00 | $-43,816.00 | 2.63 |
| Weekly 3-initial / 2-add / 8-max / interval=2 | 3 | 2 | 8 | 2 | $148,817.50 | $-60,846.50 | 2.45 |
| Weekly 1-initial / 2-add / 6-max / interval=2 | 1 | 2 | 6 | 2 | $109,414.50 | $-44,825.50 | 2.44 |
| Custom ladder 1/2/2/2/1 / 6-max / interval=2 | 1 | 1 | 6 | 2 | $109,414.50 | $-44,825.50 | 2.44 |
| Weekly 1-initial / 1-add / 6-max / interval=1 | 1 | 1 | 6 | 1 | $111,511.00 | $-45,856.00 | 2.43 |
| Weekly 3-initial / 1-add / 6-max / interval=2 | 3 | 1 | 6 | 2 | $110,895.50 | $-47,523.50 | 2.33 |
| Weekly 2-initial / 2-add / 6-max / interval=4 | 2 | 2 | 6 | 4 | $97,252.00 | $-48,640.00 | 2.00 |

### NQ

| Sizing | Init | Add | Max | Intv | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---:|---:|---:|
| Daily ladder 1/1/2/2/2/1 / 10-max / interval=2 | 1 | 1 | 10 | 2 | $1,572,142.00 | $-255,950.00 | 6.14 |
| Daily 3-initial / 1-add / 10-max / interval=2 | 3 | 1 | 10 | 2 | $1,717,280.50 | $-309,068.50 | 5.56 |
| Daily 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | $1,407,832.00 | $-299,903.00 | 4.69 |
| Daily 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | $1,456,261.50 | $-312,729.50 | 4.66 |
| Weekly 2/3/6/intv=2 (no entry guard) | 2 | 3 | 6 | 2 | $1,770,601.00 | $-476,134.00 | 3.72 |
| Weekly 2-initial / 3-add / 6-max / interval=2 | 2 | 3 | 6 | 2 | $1,443,304.50 | $-428,513.00 | 3.37 |
| Weekly 2-initial / 2-add / 5-max / interval=2 | 2 | 2 | 5 | 2 | $1,191,889.00 | $-363,906.50 | 3.28 |
| Weekly 2-initial / 3-add / 8-max / interval=2 | 2 | 3 | 8 | 2 | $1,857,848.50 | $-577,376.00 | 3.22 |
| Weekly 2-initial / 2-add / 6-max / interval=2 | 2 | 2 | 6 | 2 | $1,399,161.00 | $-438,338.00 | 3.19 |
| Weekly 3-initial / 2-add / 8-max / interval=2 | 3 | 2 | 8 | 2 | $1,827,402.50 | $-608,600.50 | 3.00 |
| Weekly 1-initial / 2-add / 6-max / interval=2 | 1 | 2 | 6 | 2 | $1,345,616.50 | $-448,338.50 | 3.00 |
| Custom ladder 1/2/2/2/1 / 6-max / interval=2 | 1 | 1 | 6 | 2 | $1,345,616.50 | $-448,338.50 | 3.00 |
| Weekly 1-initial / 1-add / 6-max / interval=1 | 1 | 1 | 6 | 1 | $1,361,639.00 | $-459,423.50 | 2.96 |
| Weekly 3-initial / 1-add / 6-max / interval=2 | 3 | 1 | 6 | 2 | $1,368,715.00 | $-474,725.50 | 2.88 |
| Weekly 2-initial / 2-add / 6-max / interval=4 | 2 | 2 | 6 | 4 | $1,241,290.00 | $-486,618.00 | 2.55 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.