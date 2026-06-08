# MNQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 3 contract(s); add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=10; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 17.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 43; guard reentries: 30.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 60  ·  Units entered: 253  ·  Win rate: 28.3%  ·  Profit factor: 5.61
Net: +117528.50 pts ($+235,057)
Closed-trade max DD: -6345.25 pts ($-12,690)
Mark-to-market max DD: -7802.75 pts ($-15,606)
Worst stack MAE: $-8,367  ·  Avg stack MAE: $-1,369

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 7 | -149.25 | $-298 | [2019.png](2019/2019.png) |
| 2020 | 6 | +38886.25 | $+77,772 | [2020.png](2020/2020.png) |
| 2021 | 9 | +18194.25 | $+36,388 | [2021.png](2021/2021.png) |
| 2022 | 10 | -4572.75 | $-9,146 | [2022.png](2022/2022.png) |
| 2023 | 10 | +14557.25 | $+29,114 | [2023.png](2023/2023.png) |
| 2024 | 8 | +34767.50 | $+69,535 | [2024.png](2024/2024.png) |
| 2025 | 11 | +17367.75 | $+34,736 | [2025.png](2025/2025.png) |
| 2026 | 2 | -1522.50 | $-3,045 | [2026.png](2026/2026.png) |
