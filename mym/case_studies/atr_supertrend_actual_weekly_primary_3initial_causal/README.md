# MYM ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 3; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 2.
Yearly ORB first-entry filter: none; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 0. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 23; guard reentries: 22.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 26  ·  Units entered: 112  ·  Win rate: 11.5%  ·  Profit factor: 3.52
Net: +80592.00 pts ($+40,296)
Closed-trade max DD: -20485.00 pts ($-10,242)
Mark-to-market max DD: -53916.00 pts ($-26,958)
Worst stack MAE: $-5,026  ·  Avg stack MAE: $-1,106

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 0 | +0.00 | $+0 | [2019.png](2019/2019.png) |
| 2020 | 4 | -6260.00 | $-3,130 | [2020.png](2020/2020.png) |
| 2021 | 0 | +0.00 | $+0 | [2021.png](2021/2021.png) |
| 2022 | 5 | +64230.00 | $+32,115 | [2022.png](2022/2022.png) |
| 2023 | 13 | -17540.00 | $-8,770 | [2023.png](2023/2023.png) |
| 2024 | 1 | +0.00 | $+0 | [2024.png](2024/2024.png) |
| 2025 | 6 | +33611.00 | $+16,806 | [2025.png](2025/2025.png) |
| 2026 | 1 | +6551.00 | $+3,276 | [2026.png](2026/2026.png) |
