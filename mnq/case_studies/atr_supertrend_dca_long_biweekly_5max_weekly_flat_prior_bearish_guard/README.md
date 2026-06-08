# MNQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=5; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 17.
Prior bearish stop guard: exit-reclaim; guard exits: 22; guard reentries: 9.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 39  ·  Units entered: 93  ·  Win rate: 35.9%  ·  Profit factor: 10.55
Net: +67187.25 pts ($+134,374)
Closed-trade max DD: -2804.75 pts ($-5,610)
Mark-to-market max DD: -4002.50 pts ($-8,005)
Worst stack MAE: $-2,789  ·  Avg stack MAE: $-773

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 4 | +122.25 | $+244 | [2019.png](2019/2019.png) |
| 2020 | 6 | +19755.50 | $+39,511 | [2020.png](2020/2020.png) |
| 2021 | 6 | +9386.25 | $+18,772 | [2021.png](2021/2021.png) |
| 2022 | 7 | -1704.00 | $-3,408 | [2022.png](2022/2022.png) |
| 2023 | 5 | +10106.00 | $+20,212 | [2023.png](2023/2023.png) |
| 2024 | 6 | +19860.25 | $+39,720 | [2024.png](2024/2024.png) |
| 2025 | 7 | +9827.50 | $+19,655 | [2025.png](2025/2025.png) |
| 2026 | 1 | -166.50 | $-333 | [2026.png](2026/2026.png) |
