# Hourly Gap Fill Study Summary

This is separate from the yearly ORB study. It checks whether RTH gaps tend to fill using the 1-minute source for fill detection, with weekly inspection charts generated as 4-hour candles.

Definitions:

- Daily gap: prior trading day 16:00 ET close to current day 09:30 ET open; filled if price trades back to the prior close during the same 09:30-16:00 ET RTH session.
- Weekly gap: previous week final RTH close to first trading day 09:30 ET open; filled if price trades back to the prior close any time before the end of that trading week.

## Results

| Market | Gap Type | Gaps | Filled | Fill Rate | Median Gap | Avg Gap | Max Gap | Weekly Charts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Daily | 1,427 | 870 | 61.0% | 58.50 | 87.21 | 830.00 | n/a |
| MNQ | Weekly | 362 | 286 | 79.0% | 58.50 | 102.71 | 998.75 | 362 |
| NQ | Daily | 3,199 | 2,020 | 63.1% | 21.00 | 47.34 | 822.25 | n/a |
| NQ | Weekly | 817 | 661 | 80.9% | 22.75 | 53.96 | 999.25 | 817 |

## Read

The weekly gap fill rate is high enough to warrant further investigation on both samples. The edge is not simply "all gaps fill": larger gaps fill less often, but even the largest weekly gap quartile stayed above 60% on MNQ and 66% on NQ in this run.

The daily gap fill rate is also meaningful, but weaker and more size-sensitive. On both instruments the smallest daily gap quartile filled around 87-88%, while the largest quartile fell to 32% on MNQ and 41.7% on NQ.

## Big Weekly Gap Follow-Up

The big-gap follow-up now has both filled and unfilled 1-hour chart sets, plus a first-pass strategy test that enters only after a 1-hour break-in candle closes at least halfway toward the prior weekly close.

| Market | Big Unfilled 1h Charts | Strategy Trades | Net | Max DD | Win Rate | Profit Factor | Strategy Charts |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 44 | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 | 91 |
| NQ | 84 | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 | 143 |

Read: the first strategy version is a useful inspection baseline, but it is not clean enough yet. It is positive gross, but drawdown is high and the edge depends heavily on a minority of TP2/end-of-week outcomes. The unfilled big-gap charts are the next place to look for entry filters that avoid weak break-ins.

## Main Live-Test Candidate

The current gap-analysis live-test candidate is **big gap-up short fade after bearish delivery change**. It uses the break-close delivery trigger, takes only shorts, and exits 3 units at halfway plus 2 units at TP1/gap fill.

| Market | Trades | Net | Max DD | Win Rate | Profit Factor | Avg MAE | Winner Charts | Loser Charts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 33 | $8,383.25 | $-3,451.00 | 42.4% | 1.80 | 55.02 pts | 14 | 19 |
| NQ | 53 | $69,242.50 | $-44,047.50 | 39.6% | 1.46 | 45.67 pts | 21 | 32 |

Read: this is the strongest gap-analysis candidate so far because it isolates the side that actually carried the delivery-change work: big gap-up fades after bearish structure. It is promoted for chart review and live-test design, not immediate automation.

### 2:2:2 EOD Runner Test

The 2:2:2 follow-up used 6 units: 2 off halfway, 2 off at TP1/gap fill, and 2 runners to the same ET calendar day's last available bar with breakeven stop after TP1. It did not improve the promoted candidate.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Main candidate | 33 | $8,383.25 | $-3,451.00 | 42.4% | 1.80 |
| MNQ | 2:2:2 EOD runner + BE | 37 | $4,568.50 | $-2,946.00 | 40.5% | 1.42 |
| NQ | Main candidate | 53 | $69,242.50 | $-44,047.50 | 39.6% | 1.46 |
| NQ | 2:2:2 EOD runner + BE | 58 | $34,570.00 | $-51,945.00 | 37.9% | 1.21 |

### Protective Exit Variants

The baseline did not move the runner stop to breakeven after TP1. No-chart follow-ups show that BE and boundary-close exits improve hit rate but remove too much runner profit.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Baseline | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 |
| MNQ | BE after TP1 | 91 | $-672.75 | $-12,025.50 | 46.2% | 0.98 |
| MNQ | BE + boundary close | 91 | $-50.75 | $-12,054.25 | 45.1% | 1.00 |
| MNQ | Swing stop + BE + boundary close | 60 | $-6,829.25 | $-12,886.75 | 56.7% | 0.79 |
| NQ | Baseline | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 |
| NQ | BE after TP1 | 143 | $9,472.50 | $-106,880.00 | 51.7% | 1.02 |
| NQ | BE + boundary close | 145 | $120.00 | $-109,932.50 | 48.3% | 1.00 |
| NQ | Swing stop + BE + boundary close | 99 | $-33,297.50 | $-133,290.00 | 60.6% | 0.91 |

### Delivery-Change Entry

The delivery-change version waits for 1-hour market structure before placing the pullback limit. It is more selective, but still marginal.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Break-in baseline | 91 | $2,047.25 | $-11,180.25 | 39.6% | 1.06 |
| MNQ | Delivery-change entry | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 |
| NQ | Break-in baseline | 143 | $43,622.50 | $-97,110.00 | 39.9% | 1.11 |
| NQ | Delivery-change entry | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 |

Read: this entry cuts trades and a little drawdown, but not enough to make the strategy attractive. The best clue is side split: delivery-change shorts were positive while longs were negative across both markets.

### Halfway-Heavy Scaleout

The break-close delivery trigger improved when the TP2 runner was removed and size was paid sooner: 3 units at halfway to the gap fill and 2 units at TP1.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Break-close classic scaleout | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 |
| MNQ | Break-close 3 halfway / 2 TP1 | 60 | $3,521.25 | $-8,457.50 | 43.3% | 1.13 |
| NQ | Break-close classic scaleout | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 |
| NQ | Break-close 3 halfway / 2 TP1 | 89 | $39,057.50 | $-92,500.00 | 42.7% | 1.12 |

### Swing-Sequence Only

The swing-sequence-only follow-up removes the higher-high/lower-low close-through gate and enters immediately after the second swing confirms. This catches some attractive individual cases, but it is not viable broadly.

| Market | Variant | Trades | Net | Max DD | Win Rate | Profit Factor |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Break-close delivery | 60 | $192.75 | $-9,003.75 | 28.3% | 1.01 |
| MNQ | Swing-sequence only, max 2/week | 140 | $-75,791.00 | $-81,789.25 | 13.6% | 0.36 |
| MNQ | Swing-sequence only, max 3/week | 187 | $-110,960.50 | $-121,620.00 | 12.3% | 0.34 |
| NQ | Break-close delivery | 89 | $10,942.50 | $-92,717.50 | 29.2% | 1.03 |
| NQ | Swing-sequence only, max 2/week | 289 | $-1,282,322.50 | $-1,282,322.50 | 12.8% | 0.32 |
| NQ | Swing-sequence only, max 3/week | 386 | $-1,873,592.50 | $-1,873,592.50 | 11.9% | 0.28 |

## Files

- MNQ detail: `README.md`
- MNQ weekly size/yearly ORB detail: `weekly_gap_size_yorb/README.md`
- MNQ big filled 1h charts: `big_filled_weekly_gap_1h/README.md`
- MNQ big unfilled 1h charts: `big_unfilled_weekly_gap_1h/README.md`
- MNQ big gap-fill strategy: `weekly_gap_fill_strategy_big/README.md`
- MNQ main live-test candidate: `weekly_gap_live_candidate_short_delivery_half3_tp1/README.md`
- MNQ candidate charts: `weekly_gap_live_candidate_short_delivery_half3_tp1/charts/INDEX.md`
- MNQ 2:2:2 EOD runner test: `weekly_gap_candidate_short_delivery_222_eod_be/README.md`
- MNQ BE after TP1: `weekly_gap_fill_strategy_big_be_tp1/README.md`
- MNQ BE + boundary close: `weekly_gap_fill_strategy_big_break_be_boundary_close/README.md`
- MNQ swing stop + BE + boundary close: `weekly_gap_fill_strategy_big_swing_be_boundary_close/README.md`
- MNQ delivery-change entry: `weekly_gap_delivery_change_strategy_big/README.md`
- MNQ break-close 3 halfway / 2 TP1: `weekly_gap_delivery_break_close_half3_tp1_2/README.md`
- MNQ swing-sequence only, max 2/week: `weekly_gap_delivery_swing_sequence_big_2week/README.md`
- MNQ swing-sequence only, max 3/week: `weekly_gap_delivery_swing_sequence_big_3week/README.md`
- MNQ daily CSV: `daily_gap_fills.csv`
- MNQ weekly CSV: `weekly_gap_fills.csv`
- MNQ weekly charts: `weekly_gap_4h/INDEX.md`
- NQ detail: `../../../nq/case_studies/gap_analysis/README.md`
- NQ weekly size/yearly ORB detail: `../../../nq/case_studies/gap_analysis/weekly_gap_size_yorb/README.md`
- NQ big filled 1h charts: `../../../nq/case_studies/gap_analysis/big_filled_weekly_gap_1h/README.md`
- NQ big unfilled 1h charts: `../../../nq/case_studies/gap_analysis/big_unfilled_weekly_gap_1h/README.md`
- NQ big gap-fill strategy: `../../../nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big/README.md`
- NQ main live-test candidate: `../../../nq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/README.md`
- NQ candidate charts: `../../../nq/case_studies/gap_analysis/weekly_gap_live_candidate_short_delivery_half3_tp1/charts/INDEX.md`
- NQ 2:2:2 EOD runner test: `../../../nq/case_studies/gap_analysis/weekly_gap_candidate_short_delivery_222_eod_be/README.md`
- NQ BE after TP1: `../../../nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_be_tp1/README.md`
- NQ BE + boundary close: `../../../nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_break_be_boundary_close/README.md`
- NQ swing stop + BE + boundary close: `../../../nq/case_studies/gap_analysis/weekly_gap_fill_strategy_big_swing_be_boundary_close/README.md`
- NQ delivery-change entry: `../../../nq/case_studies/gap_analysis/weekly_gap_delivery_change_strategy_big/README.md`
- NQ break-close 3 halfway / 2 TP1: `../../../nq/case_studies/gap_analysis/weekly_gap_delivery_break_close_half3_tp1_2/README.md`
- NQ swing-sequence only, max 2/week: `../../../nq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_2week/README.md`
- NQ swing-sequence only, max 3/week: `../../../nq/case_studies/gap_analysis/weekly_gap_delivery_swing_sequence_big_3week/README.md`
- NQ weekly charts: `../../../nq/case_studies/gap_analysis/weekly_gap_4h/INDEX.md`
- Weekly size/yearly ORB cross-market summary: `WEEKLY_GAP_SIZE_YORB_SUMMARY.md`
- Script: `../../../scripts/hourly_gap_fill_analysis.py`
- Size/yearly ORB script: `../../../scripts/weekly_gap_size_yorb_analysis.py`
- Big filled 1h chart script: `../../../scripts/weekly_big_filled_gap_1h_charts.py`
- Big gap-fill strategy script: `../../../scripts/weekly_gap_fill_strategy.py`
- Delivery-change strategy script: `../../../scripts/weekly_gap_delivery_change_strategy.py`
