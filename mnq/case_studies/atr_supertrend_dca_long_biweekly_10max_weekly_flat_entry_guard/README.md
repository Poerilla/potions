# MNQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=10; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 17.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 43; guard reentries: 30.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 60  ·  Units entered: 138  ·  Win rate: 28.3%  ·  Profit factor: 9.00
Net: +82612.50 pts ($+165,225)
Closed-trade max DD: -3124.25 pts ($-6,248)
Mark-to-market max DD: -5093.75 pts ($-10,188)
Worst stack MAE: $-2,804  ·  Avg stack MAE: $-610

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 7 | -89.75 | $-180 | [2019.png](2019/2019.png) |
| 2020 | 6 | +31325.00 | $+62,650 | [2020.png](2020/2020.png) |
| 2021 | 9 | +10432.75 | $+20,866 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1655.75 | $-3,312 | [2022.png](2022/2022.png) |
| 2023 | 10 | +9877.00 | $+19,754 | [2023.png](2023/2023.png) |
| 2024 | 8 | +20965.50 | $+41,931 | [2024.png](2024/2024.png) |
| 2025 | 11 | +12265.25 | $+24,530 | [2025.png](2025/2025.png) |
| 2026 | 2 | -507.50 | $-1,015 | [2026.png](2026/2026.png) |
