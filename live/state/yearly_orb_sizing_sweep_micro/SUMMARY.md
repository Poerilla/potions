# Yearly ORB Scaleout3 Sizing Sweep

Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for 
`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` 
path used by `broker_like_replays.py`.

Realism baseline: `slippage_ticks=1`, `fee_per_unit=$1.50`, 
stop gap-through ON, stop-first same-bar ordering, OCO-collapsed risk projection.

Ranking is by `Net / Stress DD`.

| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | RC | Units | Trades | Net | Stress DD | Net / Stress |
|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | ES | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 511 | 73 | $657,146.00 | $-66,346.00 | 9.90 |
| 2 | ES | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 292 | 73 | $395,774.50 | $-41,103.00 | 9.63 |
| 3 | ES | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 584 | 73 | $791,549.00 | $-82,206.00 | 9.63 |
| 4 | ES | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 438 | 73 | $590,099.25 | $-61,654.50 | 9.57 |
| 5 | ES | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 584 | 73 | $724,192.75 | $-75,824.00 | 9.55 |
| 6 | ES | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 438 | 73 | $529,868.00 | $-56,868.00 | 9.32 |
| 7 | ES | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 511 | 73 | $731,627.25 | $-81,506.00 | 8.98 |
| 8 | ES | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 438 | 73 | $657,455.50 | $-80,806.00 | 8.14 |
| 9 | ES | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 219 | 73 | $328,727.75 | $-40,403.00 | 8.14 |
| 10 | ES | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 657 | 73 | $986,183.25 | $-121,209.00 | 8.14 |
| 11 | ES | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 511 | 73 | $777,608.50 | $-100,657.50 | 7.73 |
| 12 | ES | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 584 | 73 | $926,261.50 | $-120,509.00 | 7.69 |
| 13 | YM | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 486 | 81 | $515,736.00 | $-67,525.00 | 7.64 |
| 14 | YM | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 648 | 81 | $697,234.25 | $-91,610.00 | 7.61 |
| 15 | YM | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 567 | 81 | $621,574.50 | $-81,932.50 | 7.59 |
| 16 | YM | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 324 | 81 | $364,416.50 | $-48,170.00 | 7.57 |
| 17 | YM | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 648 | 81 | $728,833.00 | $-96,340.00 | 7.57 |
| 18 | YM | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 486 | 81 | $545,914.75 | $-72,255.00 | 7.56 |
| 19 | YM | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 567 | 81 | $654,593.25 | $-86,662.50 | 7.55 |
| 20 | ES | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 365 | 73 | $597,533.75 | $-80,106.00 | 7.46 |
| 21 | YM | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 243 | 81 | $288,756.75 | $-39,810.00 | 7.25 |
| 22 | YM | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 486 | 81 | $577,513.50 | $-79,620.00 | 7.25 |
| 23 | YM | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 729 | 81 | $866,270.25 | $-119,430.00 | 7.25 |
| 24 | ES | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 511 | 73 | $859,214.75 | $-119,925.00 | 7.16 |
| 25 | ES | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 511 | 73 | $852,089.75 | $-119,925.00 | 7.11 |
| 26 | YM | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 567 | 81 | $681,932.00 | $-99,525.00 | 6.85 |
| 27 | YM | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 648 | 81 | $792,030.50 | $-119,430.00 | 6.63 |
| 28 | YM | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 405 | 81 | $503,273.75 | $-79,620.00 | 6.32 |
| 29 | YM | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 567 | 81 | $716,370.75 | $-119,430.00 | 6.00 |
| 30 | YM | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 567 | 81 | $714,950.75 | $-119,430.00 | 5.99 |
| 31 | MYM | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 162 | 27 | $28,376.00 | $-4,977.00 | 5.70 |
| 32 | MYM | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 216 | 27 | $38,277.75 | $-6,896.25 | 5.55 |
| 33 | MYM | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 189 | 27 | $33,860.00 | $-6,327.00 | 5.35 |
| 34 | MYM | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 162 | 27 | $29,442.25 | $-5,874.00 | 5.01 |
| 35 | MYM | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 108 | 27 | $19,540.50 | $-3,916.00 | 4.99 |
| 36 | MYM | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 216 | 27 | $39,081.00 | $-7,832.00 | 4.99 |
| 37 | MYM | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 189 | 27 | $34,400.25 | $-7,832.00 | 4.39 |
| 38 | ES | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 165 | 55 | $350,746.25 | $-86,332.50 | 4.06 |
| 39 | MYM | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 81 | 27 | $15,122.75 | $-3,916.00 | 3.86 |
| 40 | MYM | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 162 | 27 | $30,245.50 | $-7,832.00 | 3.86 |
| 41 | MYM | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 243 | 27 | $45,368.25 | $-11,748.00 | 3.86 |
| 42 | MYM | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 189 | 27 | $35,992.50 | $-9,790.00 | 3.68 |
| 43 | YM | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 343 | 49 | $415,290.50 | $-112,961.00 | 3.68 |
| 44 | MYM | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 216 | 27 | $40,687.50 | $-11,748.00 | 3.46 |
| 45 | ES | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 385 | 55 | $672,935.00 | $-199,017.00 | 3.38 |
| 46 | MYM | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 135 | 27 | $25,564.75 | $-7,832.00 | 3.26 |
| 47 | MYM | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 189 | 27 | $36,532.75 | $-11,748.00 | 3.11 |
| 48 | MYM | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 189 | 27 | $36,269.75 | $-11,748.00 | 3.09 |
| 49 | YM | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 147 | 49 | $182,899.50 | $-63,597.50 | 2.88 |
| 50 | MYM | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 98 | 14 | $29,578.00 | $-10,952.50 | 2.70 |
| 51 | YM | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 315 | 45 | $282,237.50 | $-106,667.50 | 2.65 |
| 52 | YM | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 135 | 45 | $128,033.75 | $-62,363.50 | 2.05 |
| 53 | MYM | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 42 | 14 | $12,097.62 | $-6,098.00 | 1.98 |
| 54 | MYM | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 91 | 13 | $19,370.50 | $-10,655.00 | 1.82 |
| 55 | ES | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 273 | 39 | $208,328.00 | $-121,131.50 | 1.72 |
| 56 | ES | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 117 | 39 | $92,037.00 | $-64,765.50 | 1.42 |
| 57 | MYM | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 39 | 13 | $7,596.62 | $-6,236.75 | 1.22 |
| 58 | MES | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | 33 | 11 | $9,878.31 | $-8,545.50 | 1.16 |
| 59 | MES | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | 77 | 11 | $18,358.25 | $-19,939.50 | 0.92 |
| 60 | MES | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | 96 | 12 | $5,341.00 | $-7,702.50 | 0.69 |
| 61 | MES | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | 84 | 12 | $4,625.25 | $-6,671.00 | 0.69 |
| 62 | MES | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | 108 | 12 | $5,864.25 | $-8,577.00 | 0.68 |
| 63 | MES | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | 36 | 12 | $1,954.75 | $-2,859.00 | 0.68 |
| 64 | MES | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | 72 | 12 | $3,909.50 | $-5,718.00 | 0.68 |
| 65 | MES | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | 84 | 12 | $4,432.75 | $-6,671.00 | 0.66 |
| 66 | MES | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | 60 | 12 | $3,386.25 | $-5,135.00 | 0.66 |
| 67 | MES | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | 96 | 12 | $4,956.00 | $-7,624.00 | 0.65 |
| 68 | MES | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | 48 | 12 | $2,478.00 | $-3,812.00 | 0.65 |
| 69 | MES | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | 72 | 12 | $3,717.00 | $-5,718.00 | 0.65 |
| 70 | MES | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | 84 | 12 | $4,240.25 | $-6,671.00 | 0.64 |
| 71 | MES | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | 84 | 12 | $4,817.75 | $-7,702.50 | 0.63 |
| 72 | MES | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | 84 | 12 | $4,817.75 | $-7,702.50 | 0.63 |
| 73 | MES | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | 96 | 12 | $4,763.50 | $-7,624.00 | 0.62 |
| 74 | MES | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | 72 | 12 | $3,524.50 | $-5,718.00 | 0.62 |
| 75 | MES | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | 49 | 7 | $5,477.75 | $-12,176.50 | 0.45 |
| 76 | MES | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | 21 | 7 | $2,009.12 | $-6,541.75 | 0.31 |

## Per-Market Ranking

### ES

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $657,146.00 | $-66,346.00 | 9.90 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $395,774.50 | $-41,103.00 | 9.63 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $791,549.00 | $-82,206.00 | 9.63 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $590,099.25 | $-61,654.50 | 9.57 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $724,192.75 | $-75,824.00 | 9.55 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $529,868.00 | $-56,868.00 | 9.32 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $731,627.25 | $-81,506.00 | 8.98 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $657,455.50 | $-80,806.00 | 8.14 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $328,727.75 | $-40,403.00 | 8.14 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $986,183.25 | $-121,209.00 | 8.14 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $777,608.50 | $-100,657.50 | 7.73 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $926,261.50 | $-120,509.00 | 7.69 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $597,533.75 | $-80,106.00 | 7.46 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $859,214.75 | $-119,925.00 | 7.16 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $852,089.75 | $-119,925.00 | 7.11 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $350,746.25 | $-86,332.50 | 4.06 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $672,935.00 | $-199,017.00 | 3.38 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $208,328.00 | $-121,131.50 | 1.72 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $92,037.00 | $-64,765.50 | 1.42 |

### MES

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $9,878.31 | $-8,545.50 | 1.16 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $18,358.25 | $-19,939.50 | 0.92 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $5,341.00 | $-7,702.50 | 0.69 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $4,625.25 | $-6,671.00 | 0.69 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $5,864.25 | $-8,577.00 | 0.68 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $1,954.75 | $-2,859.00 | 0.68 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $3,909.50 | $-5,718.00 | 0.68 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $4,432.75 | $-6,671.00 | 0.66 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $3,386.25 | $-5,135.00 | 0.66 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $4,956.00 | $-7,624.00 | 0.65 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $2,478.00 | $-3,812.00 | 0.65 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $3,717.00 | $-5,718.00 | 0.65 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $4,240.25 | $-6,671.00 | 0.64 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $4,817.75 | $-7,702.50 | 0.63 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $4,817.75 | $-7,702.50 | 0.63 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $4,763.50 | $-7,624.00 | 0.62 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $3,524.50 | $-5,718.00 | 0.62 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $5,477.75 | $-12,176.50 | 0.45 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $2,009.12 | $-6,541.75 | 0.31 |

### MYM

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $28,376.00 | $-4,977.00 | 5.70 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $38,277.75 | $-6,896.25 | 5.55 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $33,860.00 | $-6,327.00 | 5.35 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $29,442.25 | $-5,874.00 | 5.01 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $19,540.50 | $-3,916.00 | 4.99 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $39,081.00 | $-7,832.00 | 4.99 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $34,400.25 | $-7,832.00 | 4.39 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $15,122.75 | $-3,916.00 | 3.86 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $30,245.50 | $-7,832.00 | 3.86 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $45,368.25 | $-11,748.00 | 3.86 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $35,992.50 | $-9,790.00 | 3.68 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $40,687.50 | $-11,748.00 | 3.46 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $25,564.75 | $-7,832.00 | 3.26 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $36,532.75 | $-11,748.00 | 3.11 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $36,269.75 | $-11,748.00 | 3.09 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $29,578.00 | $-10,952.50 | 2.70 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $12,097.62 | $-6,098.00 | 1.98 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $19,370.50 | $-10,655.00 | 1.82 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $7,596.62 | $-6,236.75 | 1.22 |

### YM

| Sizing | TP25 | TP | Runner | Total | Entry | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | — | $515,736.00 | $-67,525.00 | 7.64 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | — | $697,234.25 | $-91,610.00 | 7.61 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | — | $621,574.50 | $-81,932.50 | 7.59 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | — | $364,416.50 | $-48,170.00 | 7.57 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | — | $728,833.00 | $-96,340.00 | 7.57 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | — | $545,914.75 | $-72,255.00 | 7.56 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | — | $654,593.25 | $-86,662.50 | 7.55 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | — | $288,756.75 | $-39,810.00 | 7.25 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | — | $577,513.50 | $-79,620.00 | 7.25 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | — | $866,270.25 | $-119,430.00 | 7.25 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | — | $681,932.00 | $-99,525.00 | 6.85 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | — | $792,030.50 | $-119,430.00 | 6.63 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | — | $503,273.75 | $-79,620.00 | 6.32 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | — | $716,370.75 | $-119,430.00 | 6.00 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | — | $714,950.75 | $-119,430.00 | 5.99 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | 20% | $415,290.50 | $-112,961.00 | 3.68 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | 20% | $182,899.50 | $-63,597.50 | 2.88 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | 20% | $282,237.50 | $-106,667.50 | 2.65 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | 20% | $128,033.75 | $-62,363.50 | 2.05 |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.