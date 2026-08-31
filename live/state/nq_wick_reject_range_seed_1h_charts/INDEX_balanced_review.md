# NQ 1h limit-retest charts — balanced review

Source: frozen `trades_primary.csv` FILLED rows only (not chart reconstruction).
Each chart: NQ **1h** candles entry −7d / +7d (~2 weeks),
seed high/low/mid, confirm 4h, break / limit-live / fill / exit, stop + TPs.
Causal assert: `seed_available < break < limit_live <= fill`.

Charts: **12** (ok=12) causal_ok=12

| # | file | event_id | slice | subset | side | net $ | R | bars | causal |
|---:|---|---|---|---|---|---:|---:|---:|---|
| 1 | `001_bal_limit_retest_1h_4h_bull_190_INV_WICK__4354.png` | `4h_bull_190_INV_WICK__4354` | dev | balanced_review | SHORT | 2337 | 1.04 | 211 | 1 |
| 2 | `002_bal_limit_retest_1h_4h_bear_267_INV_WICK__6236.png` | `4h_bear_267_INV_WICK__6236` | holdout | balanced_review | SHORT | -3458 | -1.00 | 230 | 1 |
| 3 | `003_bal_limit_retest_1h_4h_bull_233_INV_WICK__6320.png` | `4h_bull_233_INV_WICK__6320` | holdout | balanced_review | SHORT | 3962 | 1.00 | 230 | 1 |
| 4 | `004_bal_limit_retest_1h_4h_bull_281_INV_WICK__6404.png` | `4h_bull_281_INV_WICK__6404` | holdout | balanced_review | LONG | 3112 | 1.00 | 230 | 1 |
| 5 | `005_bal_limit_retest_1h_4h_bear_282_INV_WICK__6412.png` | `4h_bear_282_INV_WICK__6412` | holdout | balanced_review | SHORT | 6592 | 1.00 | 230 | 1 |
| 6 | `006_bal_limit_retest_1h_4h_bull_299_INV_WICK__6752.png` | `4h_bull_299_INV_WICK__6752` | holdout | balanced_review | LONG | -690 | -0.25 | 230 | 1 |
| 7 | `007_bal_limit_retest_1h_4h_bull_304_INV_WICK__6819.png` | `4h_bull_304_INV_WICK__6819` | holdout | balanced_review | LONG | 4707 | 1.00 | 230 | 1 |
| 8 | `008_bal_limit_retest_1h_4h_bear_303_INV_WICK__6887.png` | `4h_bear_303_INV_WICK__6887` | holdout | balanced_review | LONG | -1943 | -1.00 | 230 | 1 |
| 9 | `009_bal_limit_retest_1h_4h_bear_311_INV_WICK__7028.png` | `4h_bear_311_INV_WICK__7028` | holdout | balanced_review | SHORT | -3983 | -1.00 | 230 | 1 |
| 10 | `010_bal_limit_retest_1h_4h_bear_313_INV_WICK__7048.png` | `4h_bear_313_INV_WICK__7048` | holdout | balanced_review | SHORT | -5753 | -1.00 | 231 | 1 |
| 11 | `011_bal_limit_retest_1h_4h_bull_314_INV_WICK__7100.png` | `4h_bull_314_INV_WICK__7100` | holdout | balanced_review | LONG | -2228 | -1.00 | 230 | 1 |
| 12 | `012_bal_limit_retest_1h_4h_bull_329_INV_WICK__7592.png` | `4h_bull_329_INV_WICK__7592` | holdout | balanced_review | LONG | 5737 | 1.00 | 230 | 1 |
