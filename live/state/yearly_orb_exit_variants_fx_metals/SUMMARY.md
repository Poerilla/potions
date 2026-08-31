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
| 1 | XAUUSD | limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $997,266.80 | $-217,529.40 | 4.58 |
| 2 | XAUUSD | limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $1,088,525.00 | $-251,234.70 | 4.33 |
| 3 | XAUUSD | limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | 120 | 40 | $360,690.00 | $-83,596.80 | 4.31 |
| 4 | XAUUSD | limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | 240 | 40 | $721,380.00 | $-167,193.60 | 4.31 |
| 5 | XAUUSD | limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | 360 | 40 | $1,082,070.00 | $-250,790.40 | 4.31 |
| 6 | XAUUSD | limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | 320 | 40 | $1,130,926.60 | $-267,865.20 | 4.22 |
| 7 | XAUUSD | limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | 200 | 40 | $770,236.60 | $-184,268.40 | 4.18 |
| 8 | XAUUSD | limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | 160 | 40 | $403,091.60 | $-100,227.30 | 4.02 |
| 9 | XAUUSD | limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | 320 | 40 | $806,183.20 | $-200,454.60 | 4.02 |
| 10 | XAUUSD | limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $855,039.80 | $-217,529.40 | 3.93 |
| 11 | XAUUSD | limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | 240 | 40 | $559,008.30 | $-147,185.70 | 3.80 |
| 12 | XAUUSD | limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $743,636.90 | $-196,643.50 | 3.78 |
| 13 | XAUUSD | limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | 280 | 40 | $601,409.90 | $-163,407.70 | 3.68 |
| 14 | XAUUSD | limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | 240 | 40 | $487,894.80 | $-133,488.30 | 3.65 |
| 15 | XAUUSD | limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | 320 | 40 | $643,811.50 | $-179,629.70 | 3.58 |
| 16 | XAUUSD | limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | 288 | 48 | $442,408.85 | $-134,559.00 | 3.29 |
| 17 | XAUUSD | limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | 336 | 48 | $604,567.10 | $-185,649.35 | 3.26 |
| 18 | XAUUSD | limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | 144 | 48 | $289,860.35 | $-89,864.92 | 3.23 |
| 19 | XAUUSD | limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | 288 | 48 | $579,720.70 | $-179,729.85 | 3.23 |
| 20 | XAUUSD | limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | 432 | 48 | $869,581.05 | $-269,594.78 | 3.23 |
| 21 | XAUUSD | limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | 336 | 48 | $470,996.60 | $-147,371.20 | 3.20 |
| 22 | XAUUSD | limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | 192 | 48 | $318,448.10 | $-100,941.10 | 3.15 |
| 23 | XAUUSD | limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | 384 | 48 | $636,896.20 | $-201,882.20 | 3.15 |
| 24 | XAUUSD | limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | 336 | 48 | $812,405.55 | $-258,244.15 | 3.15 |
| 25 | XAUUSD | limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | 384 | 48 | $499,584.35 | $-160,183.40 | 3.12 |
| 26 | XAUUSD | limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | 384 | 48 | $911,519.90 | $-296,342.35 | 3.08 |
| 27 | XAUUSD | limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | 336 | 48 | $678,835.05 | $-222,775.30 | 3.05 |
| 28 | XAUUSD | limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | 336 | 48 | $882,932.15 | $-295,695.68 | 2.99 |
| 29 | XAUUSD | limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | 240 | 48 | $621,659.55 | $-210,003.37 | 2.96 |
| 30 | XAUUSD | limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | 288 | 48 | $375,623.60 | $-126,921.90 | 2.96 |
| 31 | XAUUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 273 | 91 | $216,047.25 | $-108,415.82 | 1.99 |
| 32 | XAUUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 637 | 91 | $310,854.60 | $-166,935.80 | 1.86 |
| 33 | XAGUSD | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 623 | 89 | $65,539.50 | $-50,978.50 | 1.29 |
| 34 | XAGUSD | limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | 255 | 51 | $120,924.75 | $-96,889.50 | 1.25 |
| 35 | XAGUSD | limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | 357 | 51 | $168,631.75 | $-138,122.00 | 1.22 |
| 36 | XAGUSD | limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | 408 | 51 | $170,966.50 | $-142,420.00 | 1.20 |
| 37 | XAGUSD | limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | 357 | 51 | $125,594.25 | $-105,485.50 | 1.19 |
| 38 | XAGUSD | limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | 357 | 51 | $145,455.75 | $-127,995.50 | 1.14 |
| 39 | XAGUSD | limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | 153 | 51 | $50,041.75 | $-45,530.50 | 1.10 |
| 40 | XAGUSD | limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | 306 | 51 | $100,083.50 | $-91,061.00 | 1.10 |
| 41 | XAGUSD | limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | 459 | 51 | $150,125.25 | $-136,591.50 | 1.10 |
| 42 | XAGUSD | limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | 235 | 47 | $111,558.75 | $-105,329.50 | 1.06 |
| 43 | XAGUSD | limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | 204 | 51 | $52,376.50 | $-49,828.50 | 1.05 |
| 44 | XAGUSD | limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | 408 | 51 | $104,753.00 | $-99,657.00 | 1.05 |
| 45 | XAGUSD | limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | 329 | 47 | $155,501.75 | $-149,938.00 | 1.04 |
| 46 | XAGUSD | limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | 376 | 47 | $155,998.50 | $-155,924.00 | 1.00 |
| 47 | XAGUSD | limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | 306 | 51 | $66,976.75 | $-69,679.50 | 0.96 |
| 48 | XAGUSD | limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | 329 | 47 | $112,552.25 | $-117,301.50 | 0.96 |
| 49 | XAGUSD | limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | 329 | 47 | $132,325.75 | $-139,811.50 | 0.95 |
| 50 | XAGUSD | limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | 306 | 51 | $57,046.00 | $-60,447.50 | 0.94 |
| 51 | XAGUSD | limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | 357 | 51 | $69,311.50 | $-73,977.50 | 0.94 |
| 52 | XAGUSD | limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | 357 | 51 | $89,173.00 | $-96,487.50 | 0.92 |
| 53 | XAGUSD | limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | 408 | 51 | $71,646.25 | $-79,308.00 | 0.90 |
| 54 | XAGUSD | limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | 141 | 47 | $44,439.75 | $-50,594.50 | 0.88 |
| 55 | XAGUSD | limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | 282 | 47 | $88,879.50 | $-101,189.00 | 0.88 |
| 56 | XAGUSD | limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | 423 | 47 | $133,319.25 | $-151,783.50 | 0.88 |
| 57 | XAGUSD | limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | 188 | 47 | $44,936.50 | $-57,457.50 | 0.78 |
| 58 | XAGUSD | limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | 376 | 47 | $89,873.00 | $-114,915.00 | 0.78 |
| 59 | XAGUSD | limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | 329 | 47 | $76,087.00 | $-108,303.50 | 0.70 |
| 60 | XAGUSD | limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | 282 | 47 | $55,816.75 | $-81,123.00 | 0.69 |
| 61 | XAGUSD | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 267 | 89 | $23,155.25 | $-34,844.50 | 0.66 |
| 62 | XAGUSD | limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | 329 | 47 | $56,313.50 | $-89,825.50 | 0.63 |
| 63 | XAGUSD | limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | 282 | 47 | $45,930.00 | $-74,862.50 | 0.61 |
| 64 | XAGUSD | limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | 376 | 47 | $56,810.25 | $-98,528.00 | 0.58 |
| 65 | AUDJPY | limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | 306 | 51 | ¥-305,542 (~$-2,778) | ¥-13,083,512 (~$-118,941) | -0.02 |
| 66 | AUDJPY | limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | 408 | 51 | ¥-1,432,156 (~$-13,020) | ¥-19,427,391 (~$-176,613) | -0.07 |
| 67 | AUDJPY | limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | 357 | 51 | ¥-2,657,299 (~$-24,157) | ¥-19,462,964 (~$-176,936) | -0.14 |
| 68 | AUDJPY | limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | 306 | 51 | ¥-3,882,442 (~$-35,295) | ¥-19,498,537 (~$-177,259) | -0.20 |
| 69 | AUDJPY | limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | 204 | 51 | ¥-2,755,828 (~$-25,053) | ¥-13,154,658 (~$-119,588) | -0.21 |
| 70 | AUDJPY | limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | 408 | 51 | ¥-5,511,656 (~$-50,106) | ¥-26,309,316 (~$-239,176) | -0.21 |
| 71 | AUDJPY | limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | 357 | 51 | ¥-7,239,399 (~$-65,813) | ¥-26,811,789 (~$-243,744) | -0.27 |
| 72 | AUDJPY | limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | 153 | 51 | ¥-3,980,971 (~$-36,191) | ¥-13,190,231 (~$-119,911) | -0.30 |
| 73 | AUDJPY | limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | 306 | 51 | ¥-7,961,942 (~$-72,381) | ¥-26,380,462 (~$-239,822) | -0.30 |
| 74 | AUDJPY | limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | 459 | 51 | ¥-11,942,913 (~$-108,572) | ¥-39,570,693 (~$-359,734) | -0.30 |
| 75 | AUDJPY | limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | 357 | 51 | ¥-9,811,099 (~$-89,192) | ¥-32,293,014 (~$-293,573) | -0.30 |
| 76 | AUDJPY | limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | 408 | 51 | ¥-13,670,656 (~$-124,279) | ¥-40,073,166 (~$-364,302) | -0.34 |
| 77 | AUDJPY | limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | 255 | 51 | ¥-9,689,685 (~$-88,088) | ¥-26,882,935 (~$-244,390) | -0.36 |
| 78 | AUDJPY | limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | 357 | 51 | ¥-14,393,199 (~$-130,847) | ¥-39,641,839 (~$-360,380) | -0.36 |
| 79 | AUDJPY | limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | 357 | 51 | ¥-14,895,799 (~$-135,416) | ¥-40,108,739 (~$-364,625) | -0.37 |
| 80 | AUDJPY | limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | 462 | 77 | ¥-10,657,034 (~$-96,882) | ¥-24,859,278 (~$-225,993) | -0.43 |
| 81 | AUDJPY | limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | 616 | 77 | ¥-14,859,462 (~$-135,086) | ¥-34,559,079 (~$-314,173) | -0.43 |
| 82 | AUDJPY | limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | 539 | 77 | ¥-13,984,673 (~$-127,133) | ¥-32,062,691 (~$-291,479) | -0.44 |
| 83 | AUDJPY | limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | 462 | 77 | ¥-13,109,884 (~$-119,181) | ¥-29,566,303 (~$-268,785) | -0.44 |
| 84 | AUDJPY | limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | 616 | 77 | ¥-17,814,912 (~$-161,954) | ¥-39,733,004 (~$-361,209) | -0.45 |
| 85 | AUDJPY | limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | 308 | 77 | ¥-8,907,456 (~$-80,977) | ¥-19,866,502 (~$-180,605) | -0.45 |
| 86 | AUDJPY | limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | 539 | 77 | ¥-18,890,373 (~$-171,731) | ¥-41,476,741 (~$-377,061) | -0.46 |
| 87 | AUDJPY | limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | 462 | 77 | ¥-16,065,334 (~$-146,048) | ¥-34,740,228 (~$-315,820) | -0.46 |
| 88 | AUDJPY | limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | 693 | 77 | ¥-24,098,001 (~$-219,073) | ¥-52,110,342 (~$-473,730) | -0.46 |
| 89 | AUDJPY | limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | 231 | 77 | ¥-8,032,667 (~$-73,024) | ¥-17,370,114 (~$-157,910) | -0.46 |
| 90 | AUDJPY | limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | 539 | 77 | ¥-17,442,723 (~$-158,570) | ¥-37,703,516 (~$-342,759) | -0.46 |
| 91 | AUDJPY | limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | 616 | 77 | ¥-23,725,812 (~$-215,689) | ¥-50,080,854 (~$-455,280) | -0.47 |
| 92 | AUDJPY | limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | 539 | 77 | ¥-22,348,423 (~$-203,167) | ¥-47,117,566 (~$-428,342) | -0.47 |
| 93 | AUDJPY | limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | 385 | 77 | ¥-15,693,145 (~$-142,665) | ¥-32,710,740 (~$-297,370) | -0.48 |
| 94 | AUDJPY | limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | 539 | 77 | ¥-22,851,023 (~$-207,737) | ¥-47,584,466 (~$-432,586) | -0.48 |
| 95 | AUDJPY | limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | 1022 | 146 | ¥-16,123,954 (~$-146,581) | ¥-27,604,543 (~$-250,950) | -0.58 |
| 96 | AUDJPY | limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | 438 | 146 | ¥-10,320,791 (~$-93,825) | ¥-13,584,524 (~$-123,496) | -0.76 |

## Per-Market Ranking

### AUDJPY

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | ¥-305,542 | ¥-13,083,512 | -0.02 |
| limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | ¥-1,432,156 | ¥-19,427,391 | -0.07 |
| limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | ¥-2,657,299 | ¥-19,462,964 | -0.14 |
| limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | ¥-3,882,442 | ¥-19,498,537 | -0.20 |
| limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | ¥-2,755,828 | ¥-13,154,658 | -0.21 |
| limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | ¥-5,511,656 | ¥-26,309,316 | -0.21 |
| limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | ¥-7,239,399 | ¥-26,811,789 | -0.27 |
| limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | ¥-3,980,971 | ¥-13,190,231 | -0.30 |
| limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | ¥-7,961,942 | ¥-26,380,462 | -0.30 |
| limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | ¥-11,942,913 | ¥-39,570,693 | -0.30 |
| limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | ¥-9,811,099 | ¥-32,293,014 | -0.30 |
| limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | ¥-13,670,656 | ¥-40,073,166 | -0.34 |
| limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | ¥-9,689,685 | ¥-26,882,935 | -0.36 |
| limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | ¥-14,393,199 | ¥-39,641,839 | -0.36 |
| limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | ¥-14,895,799 | ¥-40,108,739 | -0.37 |
| limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | ¥-10,657,034 | ¥-24,859,278 | -0.43 |
| limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | ¥-14,859,462 | ¥-34,559,079 | -0.43 |
| limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | ¥-13,984,673 | ¥-32,062,691 | -0.44 |
| limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | ¥-13,109,884 | ¥-29,566,303 | -0.44 |
| limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | ¥-17,814,912 | ¥-39,733,004 | -0.45 |
| limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | ¥-8,907,456 | ¥-19,866,502 | -0.45 |
| limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | ¥-18,890,373 | ¥-41,476,741 | -0.46 |
| limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | ¥-16,065,334 | ¥-34,740,228 | -0.46 |
| limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | ¥-24,098,001 | ¥-52,110,342 | -0.46 |
| limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | ¥-8,032,667 | ¥-17,370,114 | -0.46 |
| limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | ¥-17,442,723 | ¥-37,703,516 | -0.46 |
| limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | ¥-23,725,812 | ¥-50,080,854 | -0.47 |
| limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | ¥-22,348,423 | ¥-47,117,566 | -0.47 |
| limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | ¥-15,693,145 | ¥-32,710,740 | -0.48 |
| limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | ¥-22,851,023 | ¥-47,584,466 | -0.48 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | ¥-16,123,954 | ¥-27,604,543 | -0.58 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | ¥-10,320,791 | ¥-13,584,524 | -0.76 |

### XAGUSD

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $65,539.50 | $-50,978.50 | 1.29 |
| limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | $120,924.75 | $-96,889.50 | 1.25 |
| limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | $168,631.75 | $-138,122.00 | 1.22 |
| limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | $170,966.50 | $-142,420.00 | 1.20 |
| limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | $125,594.25 | $-105,485.50 | 1.19 |
| limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | $145,455.75 | $-127,995.50 | 1.14 |
| limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | $50,041.75 | $-45,530.50 | 1.10 |
| limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | $100,083.50 | $-91,061.00 | 1.10 |
| limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | $150,125.25 | $-136,591.50 | 1.10 |
| limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | $111,558.75 | $-105,329.50 | 1.06 |
| limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | $52,376.50 | $-49,828.50 | 1.05 |
| limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | $104,753.00 | $-99,657.00 | 1.05 |
| limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | $155,501.75 | $-149,938.00 | 1.04 |
| limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | $155,998.50 | $-155,924.00 | 1.00 |
| limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | $66,976.75 | $-69,679.50 | 0.96 |
| limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | $112,552.25 | $-117,301.50 | 0.96 |
| limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | $132,325.75 | $-139,811.50 | 0.95 |
| limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | $57,046.00 | $-60,447.50 | 0.94 |
| limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | $69,311.50 | $-73,977.50 | 0.94 |
| limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | $89,173.00 | $-96,487.50 | 0.92 |
| limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | $71,646.25 | $-79,308.00 | 0.90 |
| limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | $44,439.75 | $-50,594.50 | 0.88 |
| limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | $88,879.50 | $-101,189.00 | 0.88 |
| limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | $133,319.25 | $-151,783.50 | 0.88 |
| limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | $44,936.50 | $-57,457.50 | 0.78 |
| limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | $89,873.00 | $-114,915.00 | 0.78 |
| limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | $76,087.00 | $-108,303.50 | 0.70 |
| limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | $55,816.75 | $-81,123.00 | 0.69 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $23,155.25 | $-34,844.50 | 0.66 |
| limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | $56,313.50 | $-89,825.50 | 0.63 |
| limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | $45,930.00 | $-74,862.50 | 0.61 |
| limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | $56,810.25 | $-98,528.00 | 0.58 |

### XAUUSD

| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| limit_retest 1/3/3 + mid-close | 1 | 3 | 3 | 7 | limit_retest | mid_close | 50% | $997,266.80 | $-217,529.40 | 4.58 |
| limit_retest 1/2/4 + mid-close | 1 | 2 | 4 | 7 | limit_retest | mid_close | 50% | $1,088,525.00 | $-251,234.70 | 4.33 |
| limit_retest 1/1/1 (baseline) + mid-close | 1 | 1 | 1 | 3 | limit_retest | mid_close | 50% | $360,690.00 | $-83,596.80 | 4.31 |
| limit_retest 2/2/2 + mid-close | 2 | 2 | 2 | 6 | limit_retest | mid_close | 50% | $721,380.00 | $-167,193.60 | 4.31 |
| limit_retest 3/3/3 + mid-close | 3 | 3 | 3 | 9 | limit_retest | mid_close | 50% | $1,082,070.00 | $-250,790.40 | 4.31 |
| limit_retest 2/2/4 + mid-close | 2 | 2 | 4 | 8 | limit_retest | mid_close | 50% | $1,130,926.60 | $-267,865.20 | 4.22 |
| limit_retest 1/1/3 + mid-close | 1 | 1 | 3 | 5 | limit_retest | mid_close | 50% | $770,236.60 | $-184,268.40 | 4.18 |
| limit_retest 2/1/1 + mid-close | 2 | 1 | 1 | 4 | limit_retest | mid_close | 50% | $403,091.60 | $-100,227.30 | 4.02 |
| limit_retest 4/2/2 + mid-close | 4 | 2 | 2 | 8 | limit_retest | mid_close | 50% | $806,183.20 | $-200,454.60 | 4.02 |
| limit_retest 3/1/3 + mid-close | 3 | 1 | 3 | 7 | limit_retest | mid_close | 50% | $855,039.80 | $-217,529.40 | 3.93 |
| limit_retest 3/2/1 + mid-close | 3 | 2 | 1 | 6 | limit_retest | mid_close | 50% | $559,008.30 | $-147,185.70 | 3.80 |
| limit_retest 2/4/1 + mid-close | 2 | 4 | 1 | 7 | limit_retest | mid_close | 50% | $743,636.90 | $-196,643.50 | 3.78 |
| limit_retest 4/2/1 + mid-close | 4 | 2 | 1 | 7 | limit_retest | mid_close | 50% | $601,409.90 | $-163,407.70 | 3.68 |
| limit_retest 4/1/1 + mid-close | 4 | 1 | 1 | 6 | limit_retest | mid_close | 50% | $487,894.80 | $-133,488.30 | 3.65 |
| limit_retest 5/2/1 + mid-close | 5 | 2 | 1 | 8 | limit_retest | mid_close | 50% | $643,811.50 | $-179,629.70 | 3.58 |
| limit_retest 3/2/1 + inside-swing-take | 3 | 2 | 1 | 6 | limit_retest | inside_swing_take | — | $442,408.85 | $-134,559.00 | 3.29 |
| limit_retest 2/4/1 + inside-swing-take | 2 | 4 | 1 | 7 | limit_retest | inside_swing_take | — | $604,567.10 | $-185,649.35 | 3.26 |
| limit_retest 1/1/1 (baseline) + inside-swing-take | 1 | 1 | 1 | 3 | limit_retest | inside_swing_take | — | $289,860.35 | $-89,864.92 | 3.23 |
| limit_retest 2/2/2 + inside-swing-take | 2 | 2 | 2 | 6 | limit_retest | inside_swing_take | — | $579,720.70 | $-179,729.85 | 3.23 |
| limit_retest 3/3/3 + inside-swing-take | 3 | 3 | 3 | 9 | limit_retest | inside_swing_take | — | $869,581.05 | $-269,594.78 | 3.23 |
| limit_retest 4/2/1 + inside-swing-take | 4 | 2 | 1 | 7 | limit_retest | inside_swing_take | — | $470,996.60 | $-147,371.20 | 3.20 |
| limit_retest 2/1/1 + inside-swing-take | 2 | 1 | 1 | 4 | limit_retest | inside_swing_take | — | $318,448.10 | $-100,941.10 | 3.15 |
| limit_retest 4/2/2 + inside-swing-take | 4 | 2 | 2 | 8 | limit_retest | inside_swing_take | — | $636,896.20 | $-201,882.20 | 3.15 |
| limit_retest 1/3/3 + inside-swing-take | 1 | 3 | 3 | 7 | limit_retest | inside_swing_take | — | $812,405.55 | $-258,244.15 | 3.15 |
| limit_retest 5/2/1 + inside-swing-take | 5 | 2 | 1 | 8 | limit_retest | inside_swing_take | — | $499,584.35 | $-160,183.40 | 3.12 |
| limit_retest 2/2/4 + inside-swing-take | 2 | 2 | 4 | 8 | limit_retest | inside_swing_take | — | $911,519.90 | $-296,342.35 | 3.08 |
| limit_retest 3/1/3 + inside-swing-take | 3 | 1 | 3 | 7 | limit_retest | inside_swing_take | — | $678,835.05 | $-222,775.30 | 3.05 |
| limit_retest 1/2/4 + inside-swing-take | 1 | 2 | 4 | 7 | limit_retest | inside_swing_take | — | $882,932.15 | $-295,695.68 | 2.99 |
| limit_retest 1/1/3 + inside-swing-take | 1 | 1 | 3 | 5 | limit_retest | inside_swing_take | — | $621,659.55 | $-210,003.37 | 2.96 |
| limit_retest 4/1/1 + inside-swing-take | 4 | 1 | 1 | 6 | limit_retest | inside_swing_take | — | $375,623.60 | $-126,921.90 | 2.96 |
| limit_retest 1/1/1 (baseline) | 1 | 1 | 1 | 3 | limit_retest | range_close | — | $216,047.25 | $-108,415.82 | 1.99 |
| limit_retest 4/2/1 | 4 | 2 | 1 | 7 | limit_retest | range_close | — | $310,854.60 | $-166,935.80 | 1.86 |

## Best sizing per market

| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |
|---|---|---:|---:|---:|---:|---|
| AUDJPY | limit_retest 4/1/1 + mid-close | 4/1/1 | ¥-305,542 | ¥-13,083,512 | -0.02 | +0.74 N/S |
| XAGUSD | limit_retest 4/2/1 | 4/2/1 | $65,539.50 | $-50,978.50 | 1.29 | +0.62 N/S |
| XAUUSD | limit_retest 1/3/3 + mid-close | 1/3/3 | $997,266.80 | $-217,529.40 | 4.58 | +2.59 N/S |

## Files

- [`summary.csv`](summary.csv) — same data, CSV.
- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.
- `states/<slug>/` — broker state, fills, orders, and report for each row.