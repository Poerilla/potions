# MNQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 6.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 21. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 16; guard reentries: 9.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 22  ·  Units entered: 61  ·  Win rate: 27.3%  ·  Profit factor: 11.30
Net: +33620.75 pts ($+67,242)
Closed-trade max DD: -1245.25 pts ($-2,490)
Mark-to-market max DD: -6404.00 pts ($-12,808)
Worst stack MAE: $-3,300  ·  Avg stack MAE: $-608

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 0 | +0.00 | $+0 | [2019.png](2019/2019.png) |
| 2020 | 3 | -225.75 | $-452 | [2020.png](2020/2020.png) |
| 2021 | 5 | +15079.00 | $+30,158 | [2021.png](2021/2021.png) |
| 2022 | 0 | +0.00 | $+0 | [2022.png](2022/2022.png) |
| 2023 | 5 | -414.50 | $-829 | [2023.png](2023/2023.png) |
| 2024 | 4 | +17858.00 | $+35,716 | [2024.png](2024/2024.png) |
| 2025 | 7 | +1324.00 | $+2,648 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
