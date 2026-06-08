# MNQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 3, then 1 per add; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 6.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 21. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 16; guard reentries: 9.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 22  ·  Units entered: 92  ·  Win rate: 27.3%  ·  Profit factor: 5.51
Net: +38943.75 pts ($+77,888)
Closed-trade max DD: -2577.75 pts ($-5,156)
Mark-to-market max DD: -5603.50 pts ($-11,207)
Worst stack MAE: $-5,470  ·  Avg stack MAE: $-1,186

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 0 | +0.00 | $+0 | [2019.png](2019/2019.png) |
| 2020 | 3 | -677.25 | $-1,354 | [2020.png](2020/2020.png) |
| 2021 | 5 | +19264.75 | $+38,530 | [2021.png](2021/2021.png) |
| 2022 | 0 | +0.00 | $+0 | [2022.png](2022/2022.png) |
| 2023 | 5 | -1243.50 | $-2,487 | [2023.png](2023/2023.png) |
| 2024 | 4 | +20194.50 | $+40,389 | [2024.png](2024/2024.png) |
| 2025 | 7 | +1405.25 | $+2,810 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
