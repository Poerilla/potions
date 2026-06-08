# MNQ Monthly ORB 4H Trade Studies

## New Models

**Clean-break rank<=3 scaleout runner**: first 4h breakout of the month only, skipped if the close is already beyond TP1, and that breakout candle must rank in the top 3 largest 4h high-low ranges seen so far that month. Entry is the 4h close, 3 units, unit 1 exits halfway to TP1, unit 2 exits at TP1, and the runner stops at the breakout-side OR boundary. Before TP1, a 4h close back inside the OR closes all remaining units.

**Simple 4h close + opposing OR stop**: enter at a valid 4h close outside the OR, skip if entry is already beyond TP1, target TP1, stop at the opposing OR boundary, max 3 trades/month or 2 wins/month, re-arm after a 4h close back inside the OR.

Dollar figures use the MNQ point value of $2/point per unit. The same point path on NQ would be roughly 10x the dollar P/L and drawdown.

| Variant | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily restricted boundary entry | 141 | 22,019.5 | $44,039 | $-2,394 | 50.4% | 3.58 | n/a | n/a |
| Daily restricted scaleout3 boundary entry | 139 | 52,577.0 | $105,154 | $-3,411 | 67.6% | 4.73 | 137.0 | 1,039.2 |
| 4h close restricted daily range-close | 162 | 3,617.8 | $7,236 | $-6,656 | 44.4% | 1.25 | 159.7 | 966.5 |
| 4h close restricted scaleout3 daily range-close | 151 | 6,044.7 | $12,089 | $-11,732 | 43.0% | 1.18 | 181.3 | 829.0 |
| 4h swing-stop single, re-armed | 131 | 3,939.4 | $7,879 | $-8,336 | 46.6% | 1.21 | 228.4 | 1,831.8 |
| 4h swing-stop scaleout3, re-armed | 131 | 8,445.6 | $16,891 | $-15,093 | 46.6% | 1.21 | 241.4 | 1,831.8 |
| Clean-break rank<=3 scaleout runner | 29 | 17,980.2 | $35,960 | $-7,100 | 44.8% | 3.31 | 198.7 | 695.0 |
| Simple 4h close + opposing OR stop | 139 | 3,646.0 | $7,292 | $-8,648 | 61.2% | 1.14 | 299.4 | 2,010.2 |

## Interpretation

- The clean-break rank<=3 model is only profitable if still-open runners are marked at the final available bar. Excluding marked-final runners, it has **27 closed trades**, **-6,084.6 pts**, **$-12,169**, and **$-12,691** max closed DD.
- Marked-final runner contribution is **24,064.9 pts** / **$48,130**. Treat this as open-equity sensitivity, not harvested edge.
- The simple 4h opposing-boundary model has a decent hit rate, but its profit factor and drawdown are weak. It does not beat the more selective daily restricted research variants, and it is not materially better than the 4h swing-stop branch.
- The clean-break idea has directional pulse, but the sample is thin and clustered. It needs either a better runner exit or a filter that avoids the large close-back-inside losses.

## Clean-Break Rank Filter

- Trades taken: **29**
- First-break months skipped by rank/validity: **54**
- TP1 hit on clean-break model: **12**
- Runner marked open/final instead of boundary stop: **2**

Exit reason mix:

- Close-Back-Inside-Before-TP1: **13**
- TP50+TP1+Runner-Boundary-Stop: **10**
- TP50+Close-Back-Inside-Before-TP1: **4**
- TP50+TP1+Marked-Final: **2**

## New Model Yearly Splits

### Clean-Break Rank<=3 Scaleout Runner

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 2 | -11.0 | 1 | 1 | 70.1 | 77.8 |
| 2020 | 6 | 24.4 | 3 | 3 | 191.3 | 261.8 |
| 2021 | 2 | -414.8 | 1 | 1 | 162.5 | 165.0 |
| 2022 | 6 | -2,331.0 | 3 | 3 | 295.2 | 695.0 |
| 2023 | 7 | 23,793.1 | 4 | 3 | 141.5 | 226.0 |
| 2024 | 4 | -2,434.0 | 1 | 3 | 277.6 | 438.0 |
| 2025 | 1 | -408.8 | 0 | 1 | 174.2 | 174.2 |
| 2026 | 1 | -237.8 | 0 | 1 | 101.8 | 101.8 |

### Simple 4H Close + Opposing OR Stop

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 11 | 1,685.2 | 9 | 2 | 81.9 | 184.2 |
| 2020 | 21 | 3,315.2 | 16 | 5 | 151.8 | 458.5 |
| 2021 | 19 | -880.2 | 10 | 8 | 283.3 | 902.8 |
| 2022 | 20 | -653.5 | 11 | 9 | 352.1 | 853.0 |
| 2023 | 22 | 2,319.5 | 15 | 7 | 188.9 | 565.2 |
| 2024 | 19 | -1,415.0 | 10 | 9 | 426.5 | 2010.2 |
| 2025 | 21 | -294.8 | 11 | 10 | 490.6 | 1685.8 |
| 2026 | 6 | -430.5 | 3 | 3 | 424.2 | 960.2 |

## Outputs

- `mnq/mnq_monthly_orb_clean_break_rank3_scaleout_runner.csv`
- `mnq/mnq_monthly_orb_clean_break_rank3_skips.csv`
- `mnq/mnq_monthly_orb_simple_4h_opposing_stop.csv`
