# MNQ ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 19.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 30; guard reentries: 19.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 49  ·  Units entered: 161  ·  Win rate: 30.6%  ·  Profit factor: 16.98
Net: +131892.25 pts ($+263,784)
Closed-trade max DD: -3066.75 pts ($-6,134)
Mark-to-market max DD: -6404.00 pts ($-12,808)
Worst stack MAE: $-3,209  ·  Avg stack MAE: $-741

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 4 | +168.50 | $+337 | [2019.png](2019/2019.png) |
| 2020 | 4 | +38941.25 | $+77,882 | [2020.png](2020/2020.png) |
| 2021 | 6 | +16163.00 | $+32,326 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1645.75 | $-3,292 | [2022.png](2022/2022.png) |
| 2023 | 6 | +20122.50 | $+40,245 | [2023.png](2023/2023.png) |
| 2024 | 6 | +32955.75 | $+65,912 | [2024.png](2024/2024.png) |
| 2025 | 13 | +26559.25 | $+53,118 | [2025.png](2025/2025.png) |
| 2026 | 4 | -1372.25 | $-2,744 | [2026.png](2026/2026.png) |
