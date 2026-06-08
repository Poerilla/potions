# MNQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 17.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 43; guard reentries: 30.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 60  ·  Units entered: 167  ·  Win rate: 28.3%  ·  Profit factor: 10.83
Net: +111593.50 pts ($+223,187)
Closed-trade max DD: -3939.50 pts ($-7,879)
Mark-to-market max DD: -6404.00 pts ($-12,808)
Worst stack MAE: $-4,254  ·  Avg stack MAE: $-734

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 7 | -190.00 | $-380 | [2019.png](2019/2019.png) |
| 2020 | 6 | +38171.75 | $+76,344 | [2020.png](2020/2020.png) |
| 2021 | 9 | +13764.00 | $+27,528 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1777.50 | $-3,555 | [2022.png](2022/2022.png) |
| 2023 | 10 | +15788.25 | $+31,576 | [2023.png](2023/2023.png) |
| 2024 | 8 | +28491.00 | $+56,982 | [2024.png](2024/2024.png) |
| 2025 | 11 | +17853.50 | $+35,707 | [2025.png](2025/2025.png) |
| 2026 | 2 | -507.50 | $-1,015 | [2026.png](2026/2026.png) |
