# Weekly Gap Size + Yearly ORB Alignment Cross-Market Summary

Primary alignment is open-state alignment: the 09:30 weekly open is outside the Jan-Mar yearly ORB and the gap direction matches that side.

| Market | Small Max | Medium Max | Weekly Gaps | Overall Fill | Open-Aligned Gaps | Open-Aligned Fill | Open-Aligned Not Filled | Big Open-Aligned Fill |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 38.25 | 103.17 | 362 | 79.0% | 116 | 71.6% | 33 | 52.5% |
| NQ | 10.75 | 41.00 | 817 | 80.9% | 240 | 75.8% | 58 | 61.5% |

Read: smaller weekly gaps fill most often; big gaps still fill often enough to investigate, but unfilled gaps cluster more heavily in the big bucket. Yearly ORB alignment does not make the gap immune to fills.

## Big Gap Follow-Up

Big weekly gaps are the top third of absolute weekly gaps for each market.

| Market | Big Gap Threshold | Big Gaps | Filled | Not Filled | Fill Rate | Filled 1h Charts | Unfilled 1h Charts |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | > 103.17 pts | 121 | 77 | 44 | 63.6% | 77 | 44 |
| NQ | > 41.00 pts | 270 | 186 | 84 | 68.9% | 186 | 84 |

The filled and unfilled big-gap cases are charted separately on 1-hour candles so the path into the fill, or the failure to fill, can be inspected without the compression of the 4-hour overview.

## Big Gap-Fill Strategy Pass

First pass rules: big weekly gaps only; wait for a 1-hour candle to break back into the gap and close at least halfway toward the previous weekly RTH close; place a limit at that break-in candle close after it closes. Size is 5 units: 1 off halfway to TP1, 2 off at TP1/gap fill, and 2 off at TP2 one full gap beyond the prior weekly close. Stop is the break-in candle low for longs and high for shorts. Max two filled attempts per weekly gap.

| Market | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Avg MFE | Strategy Charts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 | 82.98 pts | 132.03 pts | 91 |
| NQ | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 | 64.45 pts | 98.41 pts | 143 |

Read: this version is positive but marginal and drawdown-heavy. TP2 and end-of-week exits carry the edge while stops are frequent; shorts were weaker than longs in both samples. Treat this as a filter-discovery baseline, not a finished execution candidate. Commissions, slippage, and queue/limit-fill uncertainty are not included.

## Main Live-Test Candidate

The current gap-analysis live-test candidate is **big gap-up short fade after bearish delivery change**, using the break-close delivery trigger and the halfway-heavy scaleout.

Rules:

- Trade only big weekly gap-up cases.
- Wait for 1-hour bearish delivery change: swing low -> swing high -> lower low that closes below the prior swing low while still inside the weekly gap.
- Place a short limit at the lowest open of the consecutive up-close candles forming the swing high.
- Stop at the highest high of that source up-close candle run.
- Size 5 units: 3 off halfway to the prior weekly close, 2 off at TP1 / gap fill, no TP2 runner.
- Max 2 order attempts per signal day.

| Market | Trades | Net | Max DD | Win Rate | Profit Factor | Avg Trade | Avg MAE | Winner Charts | Loser Charts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 33 | $8,383.25 | $-3,451.00 | 42.4% | 1.80 | $254.04 | 55.02 pts | 14 | 19 |
| NQ | 53 | $69,242.50 | $-44,047.50 | 39.6% | 1.46 | $1,306.46 | 45.67 pts | 21 | 32 |

This is the best current gap-analysis branch because it isolates the side that consistently carried the delivery-change tests, removes the weaker long side, improves profit factor, and reduces drawdown materially versus the broader variants. It still needs chart-level refinement before automation.

### 2:2:2 EOD Runner Test

Tested against the main candidate: 6 units total, 2 off halfway, 2 off at TP1/gap fill, and 2 runners held to the same ET calendar day's last available bar. After TP1, the runner stop moves to breakeven on the next 1-minute bar.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE |
|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | Main candidate, 3 halfway / 2 TP1 | 33 | $8,383.25 | $-3,451.00 | 42.4% | 1.80 | 55.02 pts |
| MNQ | 2:2:2 EOD runner + BE | 37 | $4,568.50 | $-2,946.00 | 40.5% | 1.42 | 43.28 pts |
| NQ | Main candidate, 3 halfway / 2 TP1 | 53 | $69,242.50 | $-44,047.50 | 39.6% | 1.46 | 45.67 pts |
| NQ | 2:2:2 EOD runner + BE | 58 | $34,570.00 | $-51,945.00 | 37.9% | 1.21 | 37.87 pts |

Read: 2:2:2 reduced MNQ drawdown and average MAE, but cut net and profit factor hard. It also worsened NQ drawdown. It is not promoted over the main candidate.

### Breakeven / Boundary-Close Variants

The original first pass did **not** move the runner stop to breakeven after TP1. Three no-chart follow-ups were tested:

- `BE after TP1`: original break-in candle stop; after TP1, remaining units move to breakeven on the next 1-minute bar.
- `BE + boundary close`: same stop as original, plus exit remaining units on a 1-hour close back outside the weekly gap boundary.
- `Swing stop + BE + boundary close`: initial stop uses the latest causally confirmed 1-hour swing point, then BE and boundary-close rules apply.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Avg MFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Baseline | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 | 82.98 pts | 132.03 pts |
| MNQ | BE after TP1 | 91 | $-672.75 | $-12,025.50 | 46.2% | 0.98 | 64.34 pts | 110.72 pts |
| MNQ | BE + boundary close | 91 | $-50.75 | $-12,054.25 | 45.1% | 1.00 | 61.96 pts | 109.05 pts |
| MNQ | Swing stop + BE + boundary close | 60 | $-6,829.25 | $-12,886.75 | 56.7% | 0.79 | 96.82 pts | 127.45 pts |
| NQ | Baseline | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 | 64.45 pts | 98.41 pts |
| NQ | BE after TP1 | 143 | $9,472.50 | $-106,880.00 | 51.7% | 1.02 | 48.53 pts | 80.38 pts |
| NQ | BE + boundary close | 145 | $120.00 | $-109,932.50 | 48.3% | 1.00 | 45.21 pts | 78.04 pts |
| NQ | Swing stop + BE + boundary close | 99 | $-33,297.50 | $-133,290.00 | 60.6% | 0.91 | 67.11 pts | 92.33 pts |

Read: the protective variants improve hit rate and reduce average MAE in the break-candle-stop versions, but they give back most or all of the profit because the strategy depends on rare runner continuation. The 1-hour swing-stop version is not viable in this form; it cuts many candidates and the remaining trades are worse.

### Delivery-Change Entry Variant

This variant waits for a completed 1-hour change in delivery before placing the limit. Longs require swing high -> swing low -> higher high with a close above the prior swing high; shorts require swing low -> swing high -> lower low with a close below the prior swing low. The limit is placed at the source candle run: highest open of the down-close run forming the long swing low, or lowest open of the up-close run forming the short swing high. Stop is the source run extreme. Scaleout stays 5 units: 1 halfway, 2 at TP1/gap fill, 2 at TP2.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Avg MFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Break-in baseline | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 | 82.98 pts | 132.03 pts |
| MNQ | Delivery-change entry | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 | 75.98 pts | 154.73 pts |
| NQ | Break-in baseline | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 | 64.45 pts | 98.41 pts |
| NQ | Delivery-change entry | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 | 62.28 pts | 119.92 pts |

Read: delivery-change is cleaner and slightly reduces drawdown, but it is still marginal. It filters out many cases where the gap filled before structure appeared. It also changes side behavior: shorts were profitable and longs were negative in both MNQ and NQ, so any next pass should inspect gap-up fade cases separately.

### Halfway-Heavy Scaleout

This keeps the break-close delivery trigger but changes exits from the classic 1 halfway / 2 TP1 / 2 TP2 runner to 3 halfway / 2 TP1, with no TP2 runner.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Avg MFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Break-close classic scaleout | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 | 75.98 pts | 154.73 pts |
| MNQ | Break-close 3 halfway / 2 TP1 | 60 | $3,521.25 | $-8,457.50 | 43.3% | 1.13 | 73.92 pts | 130.46 pts |
| NQ | Break-close classic scaleout | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 | 62.28 pts | 119.92 pts |
| NQ | Break-close 3 halfway / 2 TP1 | 89 | $39,057.50 | $-92,500.00 | 42.7% | 1.12 | 58.86 pts | 98.92 pts |

Read: removing the TP2 runner and paying heavier at halfway improves this specific gap-fill variant. The side split still matters: longs remained negative while shorts carried the result.

### Swing-Sequence Only Follow-Up

This removes the higher-high/lower-low close-through gate and places the order as soon as the second swing in the sequence is confirmed: swing high -> swing low for longs, or swing low -> swing high for shorts. It catches some visually attractive earlier entries, but the broad sample is much worse.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Avg MFE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Break-close delivery | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 | 75.98 pts | 154.73 pts |
| MNQ | Swing-sequence only, max 2/week | 140 | $-75,791.00 | $-81,789.25 | 13.6% | 0.36 | 107.26 pts | 86.62 pts |
| MNQ | Swing-sequence only, max 3/week | 187 | $-110,960.50 | $-121,620.00 | 12.3% | 0.34 | 112.20 pts | 86.04 pts |
| NQ | Break-close delivery | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 | 62.28 pts | 119.92 pts |
| NQ | Swing-sequence only, max 2/week | 289 | $-1,282,322.50 | $-1,282,322.50 | 12.8% | 0.32 | 79.09 pts | 55.17 pts |
| NQ | Swing-sequence only, max 3/week | 386 | $-1,873,592.50 | $-1,873,592.50 | 11.9% | 0.28 | 80.88 pts | 53.19 pts |

Read: the close-through gate was doing important damage control. Allowing a third filled trade per week made the swing-sequence-only version worse, not better.

Detailed market reports:

- `mnq/case_studies/gap_analysis/weekly_gap_size_yorb/README.md`
- `nq/case_studies/gap_analysis/weekly_gap_size_yorb/README.md`
- MNQ big filled 1h charts: `mnq/case_studies/gap_analysis/big_filled_weekly_gap_1h/README.md`
- MNQ big unfilled 1h charts: `mnq/case_studies/gap_analysis/big_unfilled_weekly_gap_1h/README.md`
- MNQ big gap-fill strategy: `mnq/case_studies/gap_analysis/weekly_gap_fill_strategy_big/README.md`
- MNQ main live-test candidate: `mnq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/README.md`
- MNQ candidate charts: `mnq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/charts/INDEX.md`
- MNQ 2:2:2 EOD runner test: `mnq/case_studies/gap_analysis/weekly_gap_candidate_short_delivery_222_eod_be/README.md`
- MNQ BE after TP1: `mnq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_be_tp1/README.md`
- MNQ BE + boundary close: `mnq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_break_be_boundary_close/README.md`
- MNQ swing stop + BE + boundary close: `mnq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_swing_be_boundary_close/README.md`
- MNQ delivery-change entry: `mnq/case_studies/gap_analysis/weekly_gap_delivery_change_strategy_big/README.md`
- MNQ break-close 3 halfway / 2 TP1: `mnq/case_studies/gap_analysis/weekly_gap_delivery_break_close_half3_tp1_2/README.md`
- MNQ swing-sequence only, max 2/week: `mnq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_2week/README.md`
- MNQ swing-sequence only, max 3/week: `mnq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_3week/README.md`
- NQ big filled 1h charts: `nq/case_studies/gap_analysis/big_filled_weekly_gap_1h/README.md`
- NQ big unfilled 1h charts: `nq/case_studies/gap_analysis/big_unfilled_weekly_gap_1h/README.md`
- NQ big gap-fill strategy: `nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big/README.md`
- NQ main live-test candidate: `nq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/README.md`
- NQ candidate charts: `nq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/charts/INDEX.md`
- NQ 2:2:2 EOD runner test: `nq/case_studies/gap_analysis/weekly_gap_candidate_short_delivery_222_eod_be/README.md`
- NQ BE after TP1: `nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_be_tp1/README.md`
- NQ BE + boundary close: `nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_break_be_boundary_close/README.md`
- NQ swing stop + BE + boundary close: `nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_swing_be_boundary_close/README.md`
- NQ delivery-change entry: `nq/case_studies/gap_analysis/weekly_gap_delivery_change_strategy_big/README.md`
- NQ break-close 3 halfway / 2 TP1: `nq/case_studies/gap_analysis/weekly_gap_delivery_break_close_half3_tp1_2/README.md`
- NQ swing-sequence only, max 2/week: `nq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_2week/README.md`
- NQ swing-sequence only, max 3/week: `nq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_3week/README.md`
