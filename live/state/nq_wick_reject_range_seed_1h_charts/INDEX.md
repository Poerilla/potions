# NQ 1h limit-retest charts — ALL fills

Source: frozen `trades_primary.csv` FILLED rows only (not chart reconstruction).
Each chart: NQ **1h** candles entry −7d / +7d (~2 weeks),
seed high/low/mid, confirm 4h, break / limit-live / fill / exit, stop + TPs.
Causal assert: `seed_available < break < limit_live <= fill`.

Charts: **67** (ok=67) causal_ok=67

| # | file | event_id | slice | subset | side | net $ | R | bars | causal |
|---:|---|---|---|---|---|---:|---:|---:|---|
| 1 | `001_all_limit_retest_1h_4h_bear_1_INV_WICK__80.png` | `4h_bear_1_INV_WICK__80` | dev | all_filled | SHORT | -57 | -0.26 | 238 | 1 |
| 2 | `002_all_limit_retest_1h_4h_bull_2_INV_WICK__95.png` | `4h_bull_2_INV_WICK__95` | dev | all_filled | LONG | -339 | -0.53 | 238 | 1 |
| 3 | `003_all_limit_retest_1h_4h_bear_4_INV_WICK__138.png` | `4h_bear_4_INV_WICK__138` | dev | all_filled | LONG | 307 | 0.98 | 238 | 1 |
| 4 | `004_all_limit_retest_1h_4h_bull_10_INV_WICK__334.png` | `4h_bull_10_INV_WICK__334` | dev | all_filled | LONG | 397 | 0.99 | 238 | 1 |
| 5 | `005_all_limit_retest_1h_4h_bull_15_INV_WICK__515.png` | `4h_bull_15_INV_WICK__515` | dev | all_filled | LONG | -443 | -1.21 | 238 | 1 |
| 6 | `006_all_limit_retest_1h_4h_bear_26_INV_WICK__815.png` | `4h_bear_26_INV_WICK__815` | dev | all_filled | SHORT | -68 | -0.25 | 232 | 1 |
| 7 | `007_all_limit_retest_1h_4h_bull_35_INV_WICK__979.png` | `4h_bull_35_INV_WICK__979` | dev | all_filled | LONG | -508 | -1.00 | 238 | 1 |
| 8 | `008_all_limit_retest_1h_4h_bull_45_INV_WICK__1177.png` | `4h_bull_45_INV_WICK__1177` | dev | all_filled | LONG | -348 | -1.00 | 238 | 1 |
| 9 | `009_all_limit_retest_1h_4h_bull_40_INV_WICK__1250.png` | `4h_bull_40_INV_WICK__1250` | dev | all_filled | LONG | 652 | 0.99 | 214 | 1 |
| 10 | `010_all_limit_retest_1h_4h_bull_69_INV_WICK__1640.png` | `4h_bull_69_INV_WICK__1640` | dev | all_filled | LONG | 427 | 0.99 | 216 | 1 |
| 11 | `011_all_limit_retest_1h_4h_bear_68_INV_WICK__1653.png` | `4h_bear_68_INV_WICK__1653` | dev | all_filled | LONG | 367 | 0.99 | 233 | 1 |
| 12 | `012_all_limit_retest_1h_4h_bull_72_INV_WICK__1684.png` | `4h_bull_72_INV_WICK__1684` | dev | all_filled | LONG | -222 | -0.25 | 240 | 1 |
| 13 | `013_all_limit_retest_1h_4h_bull_79_INV_WICK__1847.png` | `4h_bull_79_INV_WICK__1847` | dev | all_filled | SHORT | -528 | -1.00 | 240 | 1 |
| 14 | `014_all_limit_retest_1h_4h_bull_82_INV_WICK__1957.png` | `4h_bull_82_INV_WICK__1957` | dev | all_filled | LONG | 1277 | 0.79 | 216 | 1 |
| 15 | `015_all_limit_retest_1h_4h_bear_96_INV_WICK__2176.png` | `4h_bear_96_INV_WICK__2176` | dev | all_filled | SHORT | 422 | 0.99 | 155 | 1 |
| 16 | `016_all_limit_retest_1h_4h_bull_97_INV_WICK__2182.png` | `4h_bull_97_INV_WICK__2182` | dev | all_filled | LONG | -978 | -1.00 | 174 | 1 |
| 17 | `017_all_limit_retest_1h_4h_bull_92_INV_WICK__2202.png` | `4h_bull_92_INV_WICK__2202` | dev | all_filled | SHORT | 574 | 0.62 | 240 | 1 |
| 18 | `018_all_limit_retest_1h_4h_bull_104_INV_WICK__2432.png` | `4h_bull_104_INV_WICK__2432` | dev | all_filled | LONG | 898 | 0.97 | 240 | 1 |
| 19 | `019_all_limit_retest_1h_4h_bear_108_INV_WICK__2520.png` | `4h_bear_108_INV_WICK__2520` | dev | all_filled | SHORT | 512 | 0.99 | 235 | 1 |
| 20 | `020_all_limit_retest_1h_4h_bull_109_INV_WICK__2532.png` | `4h_bull_109_INV_WICK__2532` | dev | all_filled | SHORT | 216 | 0.25 | 240 | 1 |
| 21 | `021_all_limit_retest_1h_4h_bear_112_INV_WICK__2733.png` | `4h_bear_112_INV_WICK__2733` | dev | all_filled | LONG | 704 | 0.73 | 229 | 1 |
| 22 | `022_all_limit_retest_1h_4h_bear_127_INV_WICK__2930.png` | `4h_bear_127_INV_WICK__2930` | dev | all_filled | LONG | -578 | -1.00 | 231 | 1 |
| 23 | `023_all_limit_retest_1h_4h_bear_130_INV_WICK__2972.png` | `4h_bear_130_INV_WICK__2972` | dev | all_filled | LONG | -153 | -0.25 | 230 | 1 |
| 24 | `024_all_limit_retest_1h_4h_bear_121_INV_WICK__3122.png` | `4h_bear_121_INV_WICK__3122` | dev | all_filled | SHORT | -97 | -0.25 | 230 | 1 |
| 25 | `025_all_limit_retest_1h_4h_bear_140_INV_WICK__3182.png` | `4h_bear_140_INV_WICK__3182` | dev | all_filled | SHORT | 352 | 0.99 | 226 | 1 |
| 26 | `026_all_limit_retest_1h_4h_bear_157_INV_WICK__3470.png` | `4h_bear_157_INV_WICK__3470` | dev | all_filled | SHORT | 100 | 0.24 | 230 | 1 |
| 27 | `027_all_limit_retest_1h_4h_bear_167_INV_WICK__3689.png` | `4h_bear_167_INV_WICK__3689` | dev | all_filled | SHORT | 447 | 0.99 | 226 | 1 |
| 28 | `028_all_limit_retest_1h_4h_bull_169_INV_WICK__3716.png` | `4h_bull_169_INV_WICK__3716` | dev | all_filled | SHORT | 937 | 0.99 | 230 | 1 |
| 29 | `029_all_limit_retest_1h_4h_bull_175_INV_WICK__3826.png` | `4h_bull_175_INV_WICK__3826` | dev | all_filled | LONG | 1202 | 1.00 | 230 | 1 |
| 30 | `030_all_limit_retest_1h_4h_bear_176_INV_WICK__3830.png` | `4h_bear_176_INV_WICK__3830` | dev | all_filled | LONG | 727 | 0.99 | 230 | 1 |
| 31 | `031_all_limit_retest_1h_4h_bear_174_INV_WICK__3836.png` | `4h_bear_174_INV_WICK__3836` | dev | all_filled | SHORT | -102 | -0.25 | 230 | 1 |
| 32 | `032_all_limit_retest_1h_4h_bull_183_INV_WICK__4318.png` | `4h_bull_183_INV_WICK__4318` | dev | all_filled | LONG | 3118 | 0.93 | 223 | 1 |
| 33 | `033_all_limit_retest_1h_4h_bull_190_INV_WICK__4354.png` | `4h_bull_190_INV_WICK__4354` | dev | all_filled | SHORT | 2337 | 1.04 | 211 | 1 |
| 34 | `034_all_limit_retest_1h_4h_bear_193_INV_WICK__4434.png` | `4h_bear_193_INV_WICK__4434` | dev | all_filled | SHORT | -383 | -0.38 | 226 | 1 |
| 35 | `035_all_limit_retest_1h_4h_bull_199_INV_WICK__4575.png` | `4h_bull_199_INV_WICK__4575` | dev | all_filled | LONG | -583 | -0.48 | 226 | 1 |
| 36 | `036_all_limit_retest_1h_4h_bear_203_INV_WICK__4628.png` | `4h_bear_203_INV_WICK__4628` | dev | all_filled | SHORT | -1138 | -1.00 | 223 | 1 |
| 37 | `037_all_limit_retest_1h_4h_bear_212_INV_WICK__4890.png` | `4h_bear_212_INV_WICK__4890` | dev | all_filled | LONG | 382 | 0.64 | 207 | 1 |
| 38 | `038_all_limit_retest_1h_4h_bull_213_INV_WICK__4970.png` | `4h_bull_213_INV_WICK__4970` | dev | all_filled | LONG | -4208 | -1.00 | 224 | 1 |
| 39 | `039_all_limit_retest_1h_4h_bull_194_INV_WICK__4998.png` | `4h_bull_194_INV_WICK__4998` | dev | all_filled | LONG | -1730 | -0.22 | 230 | 1 |
| 40 | `040_all_limit_retest_1h_4h_bull_226_INV_WICK__5137.png` | `4h_bull_226_INV_WICK__5137` | dev | all_filled | LONG | -2643 | -1.00 | 222 | 1 |
| 41 | `041_all_limit_retest_1h_4h_bear_229_INV_WICK__5190.png` | `4h_bear_229_INV_WICK__5190` | dev | all_filled | LONG | 1742 | 1.00 | 230 | 1 |
| 42 | `042_all_limit_retest_1h_4h_bear_238_INV_WICK__5413.png` | `4h_bear_238_INV_WICK__5413` | dev | all_filled | LONG | 447 | 0.25 | 224 | 1 |
| 43 | `043_all_limit_retest_1h_4h_bear_243_INV_WICK__5570.png` | `4h_bear_243_INV_WICK__5570` | dev | all_filled | SHORT | 4257 | 1.00 | 230 | 1 |
| 44 | `044_all_limit_retest_1h_4h_bear_246_INV_WICK__5623.png` | `4h_bear_246_INV_WICK__5623` | dev | all_filled | SHORT | -753 | -1.00 | 226 | 1 |
| 45 | `045_all_limit_retest_1h_4h_bear_249_INV_WICK__5674.png` | `4h_bear_249_INV_WICK__5674` | dev | all_filled | LONG | 427 | 0.25 | 230 | 1 |
| 46 | `046_all_limit_retest_1h_4h_bull_253_INV_WICK__5729.png` | `4h_bull_253_INV_WICK__5729` | dev | all_filled | SHORT | -3753 | -1.00 | 230 | 1 |
| 47 | `047_all_limit_retest_1h_4h_bull_252_INV_WICK__5794.png` | `4h_bull_252_INV_WICK__5794` | dev | all_filled | LONG | 5928 | 0.90 | 230 | 1 |
| 48 | `048_all_limit_retest_1h_4h_bear_255_INV_WICK__5829.png` | `4h_bear_255_INV_WICK__5829` | dev | all_filled | LONG | 2707 | 1.00 | 230 | 1 |
| 49 | `049_all_limit_retest_1h_4h_bull_257_INV_WICK__5932.png` | `4h_bull_257_INV_WICK__5932` | dev | all_filled | LONG | 5247 | 1.00 | 227 | 1 |
| 50 | `050_all_limit_retest_1h_4h_bull_247_INV_WICK__5998.png` | `4h_bull_247_INV_WICK__5998` | dev | all_filled | LONG | 5052 | 0.50 | 226 | 1 |
| 51 | `051_all_limit_retest_1h_4h_bull_245_INV_WICK__6084.png` | `4h_bull_245_INV_WICK__6084` | dev | all_filled | LONG | -1630 | -0.25 | 230 | 1 |
| 52 | `052_all_limit_retest_1h_4h_bull_266_INV_WICK__6098.png` | `4h_bull_266_INV_WICK__6098` | dev | all_filled | SHORT | 8192 | 1.00 | 230 | 1 |
| 53 | `053_all_limit_retest_1h_4h_bull_269_INV_WICK__6142.png` | `4h_bull_269_INV_WICK__6142` | dev | all_filled | LONG | -5233 | -1.00 | 230 | 1 |
| 54 | `054_all_limit_retest_1h_4h_bear_267_INV_WICK__6236.png` | `4h_bear_267_INV_WICK__6236` | holdout | all_filled | SHORT | -3458 | -1.00 | 230 | 1 |
| 55 | `055_all_limit_retest_1h_4h_bull_273_INV_WICK__6250.png` | `4h_bull_273_INV_WICK__6250` | holdout | all_filled | SHORT | -740 | -0.25 | 230 | 1 |
| 56 | `056_all_limit_retest_1h_4h_bull_233_INV_WICK__6320.png` | `4h_bull_233_INV_WICK__6320` | holdout | all_filled | SHORT | 3962 | 1.00 | 230 | 1 |
| 57 | `057_all_limit_retest_1h_4h_bull_281_INV_WICK__6404.png` | `4h_bull_281_INV_WICK__6404` | holdout | all_filled | LONG | 3112 | 1.00 | 230 | 1 |
| 58 | `058_all_limit_retest_1h_4h_bear_282_INV_WICK__6412.png` | `4h_bear_282_INV_WICK__6412` | holdout | all_filled | SHORT | 6592 | 1.00 | 230 | 1 |
| 59 | `059_all_limit_retest_1h_4h_bull_299_INV_WICK__6752.png` | `4h_bull_299_INV_WICK__6752` | holdout | all_filled | LONG | -690 | -0.25 | 230 | 1 |
| 60 | `060_all_limit_retest_1h_4h_bull_304_INV_WICK__6819.png` | `4h_bull_304_INV_WICK__6819` | holdout | all_filled | LONG | 4707 | 1.00 | 230 | 1 |
| 61 | `061_all_limit_retest_1h_4h_bear_303_INV_WICK__6887.png` | `4h_bear_303_INV_WICK__6887` | holdout | all_filled | LONG | -1943 | -1.00 | 230 | 1 |
| 62 | `062_all_limit_retest_1h_4h_bear_311_INV_WICK__7028.png` | `4h_bear_311_INV_WICK__7028` | holdout | all_filled | SHORT | -3983 | -1.00 | 230 | 1 |
| 63 | `063_all_limit_retest_1h_4h_bear_313_INV_WICK__7048.png` | `4h_bear_313_INV_WICK__7048` | holdout | all_filled | SHORT | -5753 | -1.00 | 231 | 1 |
| 64 | `064_all_limit_retest_1h_4h_bull_314_INV_WICK__7100.png` | `4h_bull_314_INV_WICK__7100` | holdout | all_filled | LONG | -2228 | -1.00 | 230 | 1 |
| 65 | `065_all_limit_retest_1h_4h_bull_329_INV_WICK__7592.png` | `4h_bull_329_INV_WICK__7592` | holdout | all_filled | LONG | 5737 | 1.00 | 230 | 1 |
| 66 | `066_all_limit_retest_1h_4h_bull_349_INV_WICK__8031.png` | `4h_bull_349_INV_WICK__8031` | holdout | all_filled | SHORT | -1707 | -0.25 | 230 | 1 |
| 67 | `067_all_limit_retest_1h_4h_bull_354_INV_WICK__8068.png` | `4h_bull_354_INV_WICK__8068` | holdout | all_filled | LONG | 1860 | 0.25 | 231 | 1 |
