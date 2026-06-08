# MNQ ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; start with 3 contract(s); add 1 contract every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 19.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 30; guard reentries: 19.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 49  ·  Units entered: 226  ·  Win rate: 36.7%  ·  Profit factor: 10.13
Net: +151607.00 pts ($+303,214)
Closed-trade max DD: -6650.25 pts ($-13,300)
Mark-to-market max DD: -8262.00 pts ($-16,524)
Worst stack MAE: $-4,382  ·  Avg stack MAE: $-1,167

- [Volume sidecar yearly charts](volume_charts/INDEX.md)

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2019 | 4 | +1294.75 | $+2,590 | [2019.png](2019/2019.png) |
| 2020 | 4 | +41194.75 | $+82,390 | [2020.png](2020/2020.png) |
| 2021 | 6 | +23603.00 | $+47,206 | [2021.png](2021/2021.png) |
| 2022 | 10 | -3289.50 | $-6,579 | [2022.png](2022/2022.png) |
| 2023 | 6 | +21021.25 | $+42,042 | [2023.png](2023/2023.png) |
| 2024 | 6 | +40803.25 | $+81,606 | [2024.png](2024/2024.png) |
| 2025 | 13 | +31096.25 | $+62,192 | [2025.png](2025/2025.png) |
| 2026 | 4 | -4116.75 | $-8,234 | [2026.png](2026/2026.png) |
