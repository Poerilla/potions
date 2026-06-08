# MNQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=5; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 30.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 30  ·  Units entered: 99  ·  Win rate: 50.0%  ·  Profit factor: 8.07
Net: +77528.25 pts ($+155,056)
Closed-trade max DD: -4339.00 pts ($-8,678)
Mark-to-market max DD: -5294.25 pts ($-10,588)
Worst stack MAE: $-3,366  ·  Avg stack MAE: $-1,467

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 3 | +1.75 | $+4 | [2019.png](2019/2019.png) |
| 2020 | 4 | +21451.00 | $+42,902 | [2020.png](2020/2020.png) |
| 2021 | 6 | +11043.50 | $+22,087 | [2021.png](2021/2021.png) |
| 2022 | 5 | -3330.50 | $-6,661 | [2022.png](2022/2022.png) |
| 2023 | 5 | +9605.50 | $+19,211 | [2023.png](2023/2023.png) |
| 2024 | 5 | +21500.50 | $+43,001 | [2024.png](2024/2024.png) |
| 2025 | 5 | +18782.50 | $+37,565 | [2025.png](2025/2025.png) |
| 2026 | 2 | -1526.00 | $-3,052 | [2026.png](2026/2026.png) |
