# Inside-Candle Source-Stop Scale-Out Study

Entry is the causal inside-candle-open monthly ORB source-stop setup. This study uses two units per trade package: one unit exits at 1R, then the remaining unit moves its stop to breakeven and targets either 2R or 3R.

Restricted keeps the daily close-back-inside monthly range exit. Unrestricted does not. Results are gross, before commissions/slippage. Daily OHLC cannot prove same-day ordering between 1R, BE, and runner targets, so this remains a research approximation.

## Summary

| Instrument | Variant | Runner target | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | Avg acct R | Median acct R | Avg MAE R | 1R hits | Full stops | Runner target hits | Runner BE | Range closes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | unrestricted source-stop scaleout | 2R | 77 | $23,027.50 | $-6,002.50 | 59.74% | 2.21 | 149.53 | 0.24 | 0.50 | 1.57 | 44 | 29 | 25 | 17 | 0 |
| MNQ | unrestricted source-stop scaleout | 3R | 76 | $21,281.50 | $-5,611.00 | 60.53% | 2.15 | 140.01 | 0.24 | 0.50 | 1.62 | 44 | 28 | 12 | 25 | 0 |
| MNQ | restricted source-stop scaleout | 2R | 77 | $22,446.50 | $-3,110.00 | 61.04% | 3.22 | 145.76 | 0.22 | 0.22 | 1.40 | 36 | 22 | 20 | 1 | 33 |
| MNQ | restricted source-stop scaleout | 3R | 77 | $18,399.50 | $-2,978.00 | 61.04% | 2.82 | 119.48 | 0.18 | 0.19 | 1.40 | 36 | 22 | 8 | 1 | 41 |
| NQ | unrestricted source-stop scaleout | 2R | 177 | $254,755.00 | $-59,785.00 | 58.19% | 2.09 | 71.96 | 0.16 | 0.50 | 1.59 | 100 | 71 | 47 | 46 | 0 |
| NQ | unrestricted source-stop scaleout | 3R | 175 | $242,580.00 | $-55,875.00 | 58.86% | 2.06 | 69.31 | 0.18 | 0.50 | 1.63 | 100 | 69 | 28 | 60 | 0 |
| NQ | restricted source-stop scaleout | 2R | 179 | $239,730.00 | $-30,785.00 | 56.98% | 2.81 | 66.96 | 0.10 | 0.15 | 1.33 | 82 | 57 | 35 | 9 | 77 |
| NQ | restricted source-stop scaleout | 3R | 178 | $207,990.00 | $-29,290.00 | 57.30% | 2.59 | 58.42 | 0.11 | 0.18 | 1.34 | 83 | 56 | 20 | 11 | 87 |

## Winning Trade R Counts

Account R is total package P/L divided by initial risk on both units. A 1R partial plus a 2R runner is +1.5 account R; a 1R partial plus a 3R runner is +2.0 account R.

| Instrument | Variant | Runner target | Winning trades | Wins >=1 account R | Wins >=1.5 account R | Wins >=2 account R | Runner target wins |
|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | unrestricted source-stop scaleout | 2R | 46 | 25 | 25 | 0 | 25 |
| MNQ | unrestricted source-stop scaleout | 3R | 46 | 17 | 15 | 12 | 12 |
| MNQ | restricted source-stop scaleout | 2R | 47 | 20 | 20 | 0 | 20 |
| MNQ | restricted source-stop scaleout | 3R | 47 | 13 | 10 | 8 | 8 |
| NQ | unrestricted source-stop scaleout | 2R | 103 | 49 | 47 | 0 | 47 |
| NQ | unrestricted source-stop scaleout | 3R | 103 | 36 | 32 | 28 | 28 |
| NQ | restricted source-stop scaleout | 2R | 102 | 35 | 35 | 0 | 35 |
| NQ | restricted source-stop scaleout | 3R | 102 | 24 | 21 | 20 | 20 |

## Output CSVs

- MNQ unrestricted source-stop scaleout 2R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_source_stop_scaleout_2r.csv`
- MNQ unrestricted source-stop scaleout 3R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_source_stop_scaleout_3r.csv`
- MNQ restricted source-stop scaleout 2R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_2r.csv`
- MNQ restricted source-stop scaleout 3R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_3r.csv`
- NQ unrestricted source-stop scaleout 2R: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_source_stop_scaleout_2r.csv`
- NQ unrestricted source-stop scaleout 3R: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_source_stop_scaleout_3r.csv`
- NQ restricted source-stop scaleout 2R: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_2r.csv`
- NQ restricted source-stop scaleout 3R: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted_source_stop_scaleout_3r.csv`
