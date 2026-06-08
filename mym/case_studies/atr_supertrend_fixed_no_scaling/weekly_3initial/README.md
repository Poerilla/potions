# MYM ATR Supertrend DCA Study

> **Legacy / non-promoted result.** This folder preserves the original strong run, but the Pine parity review on 2026-05-08 found that this "weekly-primary" result was not actually using the weekly ATR engine. A column-collision bug caused the Python weekly-primary path to inherit the **daily** ATR trend/stop after daily ATR columns had already been added, and the weekly-primary loop also entered on the same daily bar whose close produced the flip. Do **not** use the $81,587 result as the live-test expectation.
>
> Corrected comparison folders:
>
> - Causal daily ATR, no weekly-flat filter: `mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md`
> - Actual completed-week ATR: `mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md`
> - Pine parity script: `pine/atr_supertrend_dca_10max_entry_guard_3initial.pine`

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 3; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 26.
Yearly ORB first-entry filter: none; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 0. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 19; guard reentries: 13.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 45  ·  Units entered: 220  ·  Win rate: 57.8%  ·  Profit factor: 15.04
Net: +163174.00 pts ($+81,587)
Closed-trade max DD: -3843.00 pts ($-1,922)
Mark-to-market max DD: -14583.00 pts ($-7,292)
Worst stack MAE: $-1,348  ·  Avg stack MAE: $-345

## Pine Parity Correction

This is no longer the promoted first live-test candidate. The old result is useful as a research artifact because it explains why the chart looked like entries came from the daily ATR down-stop, but it should not be treated as a causal live model.

Corrected MYM runs from the same data:

| Variant | Net | MTM DD | Closed DD | Win Rate | PF | Read |
|---|---:|---:|---:|---:|---:|---|
| Legacy mislabeled weekly folder | $81,587 | -$7,292 | -$1,922 | 57.8% | 15.04 | Preserved here, not live-promoted |
| Causal daily ATR, no weekly-flat filter | $11,725 | -$13,602 | -$6,942 | 20.6% | 1.45 | `mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md` |
| Actual completed-week ATR | $40,296 | -$26,958 | -$10,242 | 11.5% | 3.52 | `mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md` |

The current Pine script has been changed to default to **Daily** primary signal and confirmed daily-close guard/reclaim behavior, because that is the closest tradable interpretation of the chart behavior. It will not reproduce this legacy $81k result unless lookahead-like assumptions are reintroduced.

Capital guideline:

| Step | Rule |
|---|---|
| Minimum research floor | Recalculate from the corrected Pine/Python parity run, not this legacy folder |
| Recommended first live-test sleeve | Do not fund from the legacy $81k expectation; paper-test corrected Pine first |
| Scale milestones | Suspended until corrected causal ATR runs are rebuilt and matched against TradingView |
| YM / MNQ / portfolio milestone | Use the yearly ORB or corrected future ATR reports, not this legacy artifact |

Broker note: margin is not the same thing as strategy survival capital. Tradovate has listed low day margins for micro e-minis, and CME's micro documentation describes MYM as the **$0.50/point** Micro E-mini Dow contract, but these should be verified before any live deployment. The sizing rule here is based on historical strategy MTM drawdown, not on minimum margin. External references: [Tradovate micro margins](https://tradovate.zendesk.com/hc/en-us/articles/360022599293-What-are-the-margins-for-Micro-E-Mini-Futures), [Tradovate day-margin caveat](https://tradovate.zendesk.com/hc/en-us/articles/205815997-Does-Tradovate-offer-special-margins-for-day-trading), [CME Micro E-mini FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-micro-e-mini-equity-index-futures.html).

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 7 | +7391.00 | $+3,696 | [2019.png](2019/2019.png) |
| 2020 | 8 | +25130.00 | $+12,565 | [2020.png](2020/2020.png) |
| 2021 | 8 | +22731.00 | $+11,366 | [2021.png](2021/2021.png) |
| 2022 | 8 | +12197.00 | $+6,098 | [2022.png](2022/2022.png) |
| 2023 | 4 | +5749.00 | $+2,874 | [2023.png](2023/2023.png) |
| 2024 | 6 | +50186.00 | $+25,093 | [2024.png](2024/2024.png) |
| 2025 | 8 | +40978.00 | $+20,489 | [2025.png](2025/2025.png) |
| 2026 | 1 | -1188.00 | $-594 | [2026.png](2026/2026.png) |
