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
| 1 | NQ | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | 322 | 46 | $1,258,237.00 | $-216,355.50 | 5.82 |
| 2 | NQ | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 408 | 68 | $764,503.00 | $-159,309.00 | 4.80 |
| 3 | NQ | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | 138 | 46 | $653,394.25 | $-141,210.00 | 4.63 |
| 4 | NQ | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | 544 | 68 | $1,024,209.00 | $-224,906.50 | 4.55 |
| 5 | NQ | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 476 | 68 | $917,576.00 | $-215,480.00 | 4.26 |
| 6 | NQ | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | 273 | 39 | $897,955.50 | $-214,659.50 | 4.18 |
| 7 | NQ | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | 544 | 68 | $1,102,474.00 | $-274,738.00 | 4.01 |
| 8 | NQ | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | 272 | 68 | $551,237.00 | $-137,369.00 | 4.01 |
| 9 | NQ | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | 408 | 68 | $810,943.00 | $-206,053.50 | 3.94 |
| 10 | NQ | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | 476 | 68 | $1,027,666.00 | $-265,311.50 | 3.87 |
| 11 | NQ | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | 612 | 68 | $1,333,812.00 | $-383,827.50 | 3.48 |
| 12 | NQ | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | 408 | 68 | $889,208.00 | $-255,885.00 | 3.48 |
| 13 | NQ | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 204 | 68 | $444,604.00 | $-127,942.50 | 3.48 |
| 14 | ES | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | 165 | 55 | $291,958.75 | $-86,332.50 | 3.38 |
| 15 | NQ | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | 544 | 68 | $1,259,004.00 | $-374,401.00 | 3.36 |
| 16 | NQ | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | 340 | 68 | $814,400.00 | $-246,458.50 | 3.30 |
| 17 | NQ | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | 117 | 39 | $461,838.25 | $-141,210.00 | 3.27 |
| 18 | NQ | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | 476 | 68 | $1,010,456.00 | $-315,143.00 | 3.21 |
| 19 | NQ | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | 476 | 68 | $1,152,371.00 | $-372,926.00 | 3.09 |
| 20 | NQ | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | 476 | 68 | $1,120,546.00 | $-372,926.00 | 3.00 |
| 21 | ES | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | 385 | 55 | $551,047.50 | $-199,017.00 | 2.77 |
| 22 | YM | oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | 343 | 49 | $297,290.50 | $-133,930.50 | 2.22 |
| 23 | YM | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | 315 | 45 | $211,237.50 | $-110,852.00 | 1.91 |
| 24 | YM | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 486 | 81 | $157,766.00 | $-88,868.00 | 1.78 |
| 25 | YM | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | 648 | 81 | $210,869.25 | $-122,347.75 | 1.72 |
| 26 | YM | oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | 147 | 49 | $121,154.50 | $-72,163.00 | 1.68 |
| 27 | YM | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 567 | 81 | $185,544.50 | $-111,393.50 | 1.67 |
| 28 | YM | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | 648 | 81 | $214,233.00 | $-133,919.00 | 1.60 |
| 29 | YM | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | 324 | 81 | $107,116.50 | $-66,959.50 | 1.60 |
| 30 | YM | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | 486 | 81 | $160,219.75 | $-100,439.25 | 1.60 |
| 31 | YM | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | 567 | 81 | $189,818.25 | $-126,169.25 | 1.50 |
| 32 | YM | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | 729 | 81 | $245,375.25 | $-182,552.25 | 1.34 |
| 33 | YM | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | 486 | 81 | $163,583.50 | $-121,701.50 | 1.34 |
| 34 | YM | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 243 | 81 | $81,791.75 | $-60,850.75 | 1.34 |
| 35 | YM | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | 567 | 81 | $190,452.00 | $-149,893.00 | 1.27 |
| 36 | YM | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | 648 | 81 | $220,960.50 | $-178,084.50 | 1.24 |
| 37 | YM | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | 135 | 45 | $92,733.75 | $-77,570.50 | 1.20 |
| 38 | YM | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | 405 | 81 | $139,168.75 | $-117,233.75 | 1.19 |
| 39 | ES | limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | 273 | 39 | $140,865.50 | $-121,131.50 | 1.16 |
| 40 | YM | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | 567 | 81 | $195,635.75 | $-173,616.75 | 1.13 |
| 41 | YM | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | 567 | 81 | $194,725.75 | $-173,616.75 | 1.12 |
| 42 | ES | limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | 365 | 73 | $112,421.25 | $-118,550.00 | 0.95 |
| 43 | ES | limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | 511 | 73 | $166,702.25 | $-177,825.00 | 0.94 |
| 44 | ES | limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | 511 | 73 | $160,377.25 | $-177,825.00 | 0.90 |
| 45 | ES | limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | 584 | 73 | $164,236.50 | $-189,084.00 | 0.87 |
| 46 | ES | limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | 117 | 39 | $56,712.00 | $-70,965.50 | 0.80 |
| 47 | ES | limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | 511 | 73 | $121,283.50 | $-165,448.50 | 0.73 |
| 48 | ES | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 219 | 73 | $51,815.25 | $-70,906.50 | 0.73 |
| 49 | ES | limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | 438 | 73 | $103,630.50 | $-141,813.00 | 0.73 |
| 50 | ES | limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | 657 | 73 | $155,445.75 | $-212,719.50 | 0.73 |
| 51 | ES | limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | 511 | 73 | $107,489.75 | $-165,448.50 | 0.65 |
| 52 | ES | limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | 292 | 73 | $49,349.50 | $-94,542.00 | 0.52 |
| 53 | ES | limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | 584 | 73 | $98,699.00 | $-189,084.00 | 0.52 |
| 54 | ES | limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | 438 | 73 | $70,861.75 | $-141,813.00 | 0.50 |
| 55 | ES | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 511 | 73 | $68,396.00 | $-170,343.00 | 0.40 |
| 56 | ES | limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | 584 | 73 | $65,930.25 | $-200,348.25 | 0.33 |
| 57 | ES | limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | 438 | 73 | $44,418.00 | $-153,569.00 | 0.29 |

## Per-Market Ranking

### ES

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | $291,958.75 | $-86,332.50 | 3.38 |
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | $551,047.50 | $-199,017.00 | 2.77 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | $140,865.50 | $-121,131.50 | 1.16 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | $112,421.25 | $-118,550.00 | 0.95 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | $166,702.25 | $-177,825.00 | 0.94 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | $160,377.25 | $-177,825.00 | 0.90 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | $164,236.50 | $-189,084.00 | 0.87 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | $56,712.00 | $-70,965.50 | 0.80 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | $121,283.50 | $-165,448.50 | 0.73 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $51,815.25 | $-70,906.50 | 0.73 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | $103,630.50 | $-141,813.00 | 0.73 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | $155,445.75 | $-212,719.50 | 0.73 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | $107,489.75 | $-165,448.50 | 0.65 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | $49,349.50 | $-94,542.00 | 0.52 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | $98,699.00 | $-189,084.00 | 0.52 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | $70,861.75 | $-141,813.00 | 0.50 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $68,396.00 | $-170,343.00 | 0.40 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | $65,930.25 | $-200,348.25 | 0.33 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $44,418.00 | $-153,569.00 | 0.29 |

### NQ

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | $1,258,237.00 | $-216,355.50 | 5.82 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $764,503.00 | $-159,309.00 | 4.80 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | $653,394.25 | $-141,210.00 | 4.63 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | $1,024,209.00 | $-224,906.50 | 4.55 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $917,576.00 | $-215,480.00 | 4.26 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | $897,955.50 | $-214,659.50 | 4.18 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | $1,102,474.00 | $-274,738.00 | 4.01 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | $551,237.00 | $-137,369.00 | 4.01 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | $810,943.00 | $-206,053.50 | 3.94 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | $1,027,666.00 | $-265,311.50 | 3.87 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | $1,333,812.00 | $-383,827.50 | 3.48 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | $889,208.00 | $-255,885.00 | 3.48 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $444,604.00 | $-127,942.50 | 3.48 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | $1,259,004.00 | $-374,401.00 | 3.36 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | $814,400.00 | $-246,458.50 | 3.30 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | $461,838.25 | $-141,210.00 | 3.27 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | $1,010,456.00 | $-315,143.00 | 3.21 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | $1,152,371.00 | $-372,926.00 | 3.09 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | $1,120,546.00 | $-372,926.00 | 3.00 |

### YM

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| oco_stop 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | oco_stop | range_close | 20% | $297,290.50 | $-133,930.50 | 2.22 |
| limit_retest 4/2/1 + 20% range-close | 4 | 2 | 1 | 7 | limit_retest | range_close | 20% | $211,237.50 | $-110,852.00 | 1.91 |
| limit_retest 4/1/1 | 4 | 1 | 1 | 6 | limit_retest | range_close | — | $157,766.00 | $-88,868.00 | 1.78 |
| limit_retest 5/2/1 | 5 | 2 | 1 | 8 | limit_retest | range_close | — | $210,869.25 | $-122,347.75 | 1.72 |
| oco_stop 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | oco_stop | range_close | 20% | $121,154.50 | $-72,163.00 | 1.68 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $185,544.50 | $-111,393.50 | 1.67 |
| limit_retest 4/2/2 | 4 | 2 | 2 | 8 | limit_retest | range_close | — | $214,233.00 | $-133,919.00 | 1.60 |
| limit_retest 2/1/1 | 2 | 1 | 1 | 4 | limit_retest | range_close | — | $107,116.50 | $-66,959.50 | 1.60 |
| limit_retest 3/2/1 | 3 | 2 | 1 | 6 | limit_retest | range_close | — | $160,219.75 | $-100,439.25 | 1.60 |
| limit_retest 3/1/3 | 3 | 1 | 3 | 7 | limit_retest | range_close | — | $189,818.25 | $-126,169.25 | 1.50 |
| limit_retest 3/3/3 | 3 | 3 | 3 | 9 | limit_retest | range_close | — | $245,375.25 | $-182,552.25 | 1.34 |
| limit_retest 2/2/2 | 2 | 2 | 2 | 6 | limit_retest | range_close | — | $163,583.50 | $-121,701.50 | 1.34 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $81,791.75 | $-60,850.75 | 1.34 |
| limit_retest 2/4/1 | 2 | 4 | 1 | 7 | limit_retest | range_close | — | $190,452.00 | $-149,893.00 | 1.27 |
| limit_retest 2/2/4 | 2 | 2 | 4 | 8 | limit_retest | range_close | — | $220,960.50 | $-178,084.50 | 1.24 |
| limit_retest 1/1/1 + 20% range-close | 1 | 1 | 1 | 3 | limit_retest | range_close | 20% | $92,733.75 | $-77,570.50 | 1.20 |
| limit_retest 1/1/3 | 1 | 1 | 3 | 5 | limit_retest | range_close | — | $139,168.75 | $-117,233.75 | 1.19 |
| limit_retest 1/2/4 | 1 | 2 | 4 | 7 | limit_retest | range_close | — | $195,635.75 | $-173,616.75 | 1.13 |
| limit_retest 1/3/3 | 1 | 3 | 3 | 7 | limit_retest | range_close | — | $194,725.75 | $-173,616.75 | 1.12 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| ES | oco_stop 1/1/1 + 20% range-close | 1/1/1 | $291,958.75 | $-86,332.50 | 3.38 | +2.65 N/S |
| NQ | oco_stop 4/2/1 + 20% range-close | 4/2/1 | $1,258,237.00 | $-216,355.50 | 5.82 | +2.34 N/S |
| YM | oco_stop 4/2/1 + 20% range-close | 4/2/1 | $297,290.50 | $-133,930.50 | 2.22 | +0.88 N/S |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.