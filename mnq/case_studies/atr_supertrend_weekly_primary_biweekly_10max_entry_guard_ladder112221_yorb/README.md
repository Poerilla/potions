# MNQ ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 8.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 25. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 12; guard reentries: 7.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 20  ·  Units entered: 61  ·  Win rate: 35.0%  ·  Profit factor: 15.83
Net: +36240.00 pts ($+72,480)
Closed-trade max DD: -844.50 pts ($-1,689)
Mark-to-market max DD: -6404.00 pts ($-12,808)
Worst stack MAE: $-3,209  ·  Avg stack MAE: $-556

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 0 | +0.00 | $+0 | [2019.png](2019/2019.png) |
| 2020 | 2 | -13.50 | $-27 | [2020.png](2020/2020.png) |
| 2021 | 4 | +16502.50 | $+33,005 | [2021.png](2021/2021.png) |
| 2022 | 1 | +12.75 | $+26 | [2022.png](2022/2022.png) |
| 2023 | 4 | -394.00 | $-788 | [2023.png](2023/2023.png) |
| 2024 | 3 | +18818.50 | $+37,637 | [2024.png](2024/2024.png) |
| 2025 | 9 | +1313.75 | $+2,628 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
