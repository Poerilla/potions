# NQ 1h limit-retest charts — holdout fills

Source: frozen `trades_primary.csv` FILLED rows only (not chart reconstruction).
Each chart: NQ **1h** candles entry −7d / +7d (~2 weeks),
seed high/low/mid, confirm 4h, break / limit-live / fill / exit, stop + TPs.
Causal assert: `seed_available < break < limit_live <= fill`.

Charts: **14** (ok=14) causal_ok=14

| # | file | event_id | slice | subset | side | net $ | R | bars | causal |
|---:|---|---|---|---|---|---:|---:|---:|---|
| 1 | `001_hol_limit_retest_1h_4h_bear_267_INV_WICK__6236.png` | `4h_bear_267_INV_WICK__6236` | holdout | holdout | SHORT | -3458 | -1.00 | 230 | 1 |
| 2 | `002_hol_limit_retest_1h_4h_bull_273_INV_WICK__6250.png` | `4h_bull_273_INV_WICK__6250` | holdout | holdout | SHORT | -740 | -0.25 | 230 | 1 |
| 3 | `003_hol_limit_retest_1h_4h_bull_233_INV_WICK__6320.png` | `4h_bull_233_INV_WICK__6320` | holdout | holdout | SHORT | 3962 | 1.00 | 230 | 1 |
| 4 | `004_hol_limit_retest_1h_4h_bull_281_INV_WICK__6404.png` | `4h_bull_281_INV_WICK__6404` | holdout | holdout | LONG | 3112 | 1.00 | 230 | 1 |
| 5 | `005_hol_limit_retest_1h_4h_bear_282_INV_WICK__6412.png` | `4h_bear_282_INV_WICK__6412` | holdout | holdout | SHORT | 6592 | 1.00 | 230 | 1 |
| 6 | `006_hol_limit_retest_1h_4h_bull_299_INV_WICK__6752.png` | `4h_bull_299_INV_WICK__6752` | holdout | holdout | LONG | -690 | -0.25 | 230 | 1 |
| 7 | `007_hol_limit_retest_1h_4h_bull_304_INV_WICK__6819.png` | `4h_bull_304_INV_WICK__6819` | holdout | holdout | LONG | 4707 | 1.00 | 230 | 1 |
| 8 | `008_hol_limit_retest_1h_4h_bear_303_INV_WICK__6887.png` | `4h_bear_303_INV_WICK__6887` | holdout | holdout | LONG | -1943 | -1.00 | 230 | 1 |
| 9 | `009_hol_limit_retest_1h_4h_bear_311_INV_WICK__7028.png` | `4h_bear_311_INV_WICK__7028` | holdout | holdout | SHORT | -3983 | -1.00 | 230 | 1 |
| 10 | `010_hol_limit_retest_1h_4h_bear_313_INV_WICK__7048.png` | `4h_bear_313_INV_WICK__7048` | holdout | holdout | SHORT | -5753 | -1.00 | 231 | 1 |
| 11 | `011_hol_limit_retest_1h_4h_bull_314_INV_WICK__7100.png` | `4h_bull_314_INV_WICK__7100` | holdout | holdout | LONG | -2228 | -1.00 | 230 | 1 |
| 12 | `012_hol_limit_retest_1h_4h_bull_329_INV_WICK__7592.png` | `4h_bull_329_INV_WICK__7592` | holdout | holdout | LONG | 5737 | 1.00 | 230 | 1 |
| 13 | `013_hol_limit_retest_1h_4h_bull_349_INV_WICK__8031.png` | `4h_bull_349_INV_WICK__8031` | holdout | holdout | SHORT | -1707 | -0.25 | 230 | 1 |
| 14 | `014_hol_limit_retest_1h_4h_bull_354_INV_WICK__8068.png` | `4h_bull_354_INV_WICK__8068` | holdout | holdout | LONG | 1860 | 0.25 | 231 | 1 |
