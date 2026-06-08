# MYM ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 3; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: none using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 0.
Yearly ORB first-entry filter: none; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 0. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 41; guard reentries: 31.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 63  ·  Units entered: 261  ·  Win rate: 20.6%  ·  Profit factor: 1.45
Net: +23450.00 pts ($+11,725)
Closed-trade max DD: -13885.00 pts ($-6,942)
Mark-to-market max DD: -27205.00 pts ($-13,602)
Worst stack MAE: $-3,650  ·  Avg stack MAE: $-674

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 7 | +856.00 | $+428 | [2019.png](2019/2019.png) |
| 2020 | 8 | +9236.00 | $+4,618 | [2020.png](2020/2020.png) |
| 2021 | 13 | +1841.00 | $+920 | [2021.png](2021/2021.png) |
| 2022 | 12 | -2201.00 | $-1,100 | [2022.png](2022/2022.png) |
| 2023 | 5 | +276.00 | $+138 | [2023.png](2023/2023.png) |
| 2024 | 10 | +20158.00 | $+10,079 | [2024.png](2024/2024.png) |
| 2025 | 12 | -969.00 | $-484 | [2025.png](2025/2025.png) |
| 2026 | 1 | -5747.00 | $-2,874 | [2026.png](2026/2026.png) |
