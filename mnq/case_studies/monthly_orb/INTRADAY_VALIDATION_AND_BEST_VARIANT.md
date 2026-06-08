# Monthly ORB Variant Comparison And Intraday Validation

Raw MNQ 1-minute bars were used to validate the strongest causal daily candidate: inside-candle-open restricted source-stop scaleout with a 2R runner.

Causal intraday assumptions:

- Monthly OR is still built from the first 3 daily bars.
- Breakout signal is only known after the daily close.
- The inside-candle-open limit is live on the next UTC daily bar.
- Fill is a limit touch on 1-minute bars.
- If entry and initial stop are both touched in the fill minute, the stop is counted.
- The 1R partial can trigger only after fill; BE/runner orders become active on the next minute.
- After the BE move, same-minute BE/runner ambiguity is resolved BE-first.
- Restricted range-close exits are applied at the daily close after all minute events for that date.

## Variant Comparison

| Rank | Variant | Causal? | Units | Trades | Net | Max DD | Net/unit | DD/unit | Win rate | PF | Net/DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | inside source-stop scaleout 2R restricted | yes | 2 | 77 | $22,446.50 | $-3,110.00 | $11,223.25 | $-1,555.00 | 61.04% | 3.22 | 7.22 |
| 2 | inside source-stop scaleout 3R restricted | yes | 2 | 77 | $18,399.50 | $-2,978.00 | $9,199.75 | $-1,489.00 | 61.04% | 2.82 | 6.18 |
| 3 | inside-candle-open restricted source-stop | yes | 1 | 77 | $10,291.50 | $-2,006.50 | $10,291.50 | $-2,006.50 | 49.35% | 2.74 | 5.13 |
| 4 | inside-candle-open restricted | yes | 1 | 77 | $11,453.50 | $-2,293.50 | $11,453.50 | $-2,293.50 | 54.55% | 2.43 | 4.99 |
| 5 | inside source-stop scaleout 2R unrestricted | yes | 2 | 77 | $23,027.50 | $-6,002.50 | $11,513.75 | $-3,001.25 | 59.74% | 2.21 | 3.84 |
| 6 | inside source-stop scaleout 3R unrestricted | yes | 2 | 76 | $21,281.50 | $-5,611.00 | $10,640.75 | $-2,805.50 | 60.53% | 2.15 | 3.79 |
| 7 | boundary-retest restricted | yes | 1 | 117 | $12,595.00 | $-4,479.00 | $12,595.00 | $-4,479.00 | 30.77% | 1.66 | 2.81 |
| 8 | inside-candle-open unrestricted source-stop | yes | 1 | 71 | $8,088.00 | $-3,974.50 | $8,088.00 | $-3,974.50 | 29.58% | 1.53 | 2.03 |
| 9 | inside-candle-open unrestricted | yes | 1 | 69 | $8,232.00 | $-4,963.50 | $8,232.00 | $-4,963.50 | 42.03% | 1.36 | 1.66 |
| 10 | close-entry restricted | yes | 1 | 146 | $5,072.00 | $-6,352.00 | $5,072.00 | $-6,352.00 | 53.42% | 1.16 | 0.80 |
| 11 | boundary-retest unrestricted | yes | 1 | 106 | $6,329.00 | $-8,236.50 | $6,329.00 | $-8,236.50 | 56.60% | 1.15 | 0.77 |
| 12 | close-entry restricted 2x-breakout-stop | yes | 1 | 146 | $3,439.00 | $-6,519.50 | $3,439.00 | $-6,519.50 | 47.95% | 1.11 | 0.53 |
| 13 | close-entry restricted boundary-candle-stop | yes | 1 | 146 | $3,340.50 | $-6,292.00 | $3,340.50 | $-6,292.00 | 51.37% | 1.10 | 0.53 |
| 14 | close-entry unrestricted near-boundary-stop | yes | 1 | 162 | $2,526.00 | $-7,170.50 | $2,526.00 | $-7,170.50 | 29.01% | 1.07 | 0.35 |
| 15 | close-entry unrestricted breakout-stop | yes | 1 | 156 | $1,388.50 | $-10,252.50 | $1,388.50 | $-10,252.50 | 41.03% | 1.03 | 0.14 |
| 16 | close-entry restricted near-boundary-stop | yes | 1 | 149 | $617.50 | $-4,610.00 | $617.50 | $-4,610.00 | 34.90% | 1.03 | 0.13 |
| 17 | close-entry unrestricted boundary-candle-stop | yes | 1 | 154 | $-3,188.50 | $-13,319.00 | $-3,188.50 | $-13,319.00 | 52.60% | 0.95 | -0.24 |
| 18 | close-entry unrestricted | yes | 1 | 151 | $-4,954.50 | $-14,614.50 | $-4,954.50 | $-14,614.50 | 57.62% | 0.93 | -0.34 |
| 19 | close-entry unrestricted 2x-breakout-stop | yes | 1 | 154 | $-5,995.50 | $-14,066.50 | $-5,995.50 | $-14,066.50 | 51.95% | 0.91 | -0.43 |
| 20 | close-entry restricted breakout-stop | yes | 1 | 146 | $-5,009.50 | $-12,192.50 | $-5,009.50 | $-12,192.50 | 39.73% | 0.85 | -0.41 |
| 21 | original boundary-entry restricted | no | 1 | 141 | $44,039.00 | $-2,394.00 | $44,039.00 | $-2,394.00 | 50.35% | 3.58 | 18.40 |
| 22 | original boundary-entry | no | 1 | 128 | $31,502.50 | $-5,444.50 | $31,502.50 | $-5,444.50 | 66.41% | 1.80 | 5.79 |

## Intraday Scale-Out Runner Comparison

| Variant | Runner target | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | 1R hits | Runner hits | Full stops | BE exits | Range closes | Avg MAE R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unrestricted source-stop scaleout | 2R | 76 | $12,053.50 | $-7,844.00 | 56.58% | 1.51 | 79.30 | 41 | 21 | 30 | 18 | 0 | 0.72 |
| unrestricted source-stop scaleout | 3R | 73 | $13,566.00 | $-7,617.50 | 57.53% | 1.62 | 92.92 | 40 | 13 | 28 | 21 | 0 | 0.72 |
| restricted source-stop scaleout | 2R | 77 | $12,043.00 | $-4,188.50 | 58.44% | 2.16 | 78.20 | 24 | 14 | 17 | 6 | 39 | 0.58 |
| restricted source-stop scaleout | 3R | 77 | $11,399.50 | $-4,022.00 | 58.44% | 2.10 | 74.02 | 24 | 7 | 17 | 6 | 42 | 0.58 |

## Daily Vs Intraday For Selected Candidate

| Mode | Trades | Net | Max DD | Win rate | PF | Avg/trade pts | 1R hits | Runner hits | Full stops | BE exits | Range closes | Avg MAE R | Median MAE R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily OHLC | 77 | $22,446.50 | $-3,110.00 | 61.04% | 3.22 | 145.76 | 36 | 20 | 22 | 1 | 33 | 1.40 | 0.49 |
| 1-minute causal | 77 | $12,043.00 | $-4,188.50 | 58.44% | 2.16 | 78.20 | 24 | 14 | 17 | 6 | 39 | 0.58 | 0.36 |

## Best Candidate

**Best current execution candidate: inside-candle-open restricted source-stop scaleout with a 2R runner, validated on MNQ 1-minute bars.** It is not the highest gross daily backtest row, but it has the best blend of causality, drawdown control, profit factor, and explicit risk. In the minute-level runner comparison, unrestricted 3R has the highest net, but restricted 2R has much lower drawdown and the best profit factor.

The non-causal original boundary-entry rows stay in the table for context only; they are not live-test candidates because they assume same-bar knowledge/fill behavior that the causal studies removed.

## Outputs

- Intraday CSV: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_source_stop_scaleout_2r_intraday.csv`
- Chart index: `/home/tester/hsm/potions/mnq/case_studies/monthly_orb/inside_source_stop_scaleout_2r_intraday/INDEX.md`
