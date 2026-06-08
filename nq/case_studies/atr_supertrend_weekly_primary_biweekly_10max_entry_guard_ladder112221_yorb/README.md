# NQ ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 26.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 74. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 31; guard reentries: 20.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 57  ·  Units entered: 189  ·  Win rate: 36.8%  ·  Profit factor: 13.14
Net: +53473.50 pts ($+1,069,470)
Closed-trade max DD: -1147.00 pts ($-22,940)
Mark-to-market max DD: -6410.00 pts ($-128,200)
Worst stack MAE: $-32,030  ·  Avg stack MAE: $-3,413

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 0 | +0.00 | $+0 | [2010.png](2010/2010.png) |
| 2011 | 0 | +0.00 | $+0 | [2011.png](2011/2011.png) |
| 2012 | 1 | -39.00 | $-780 | [2012.png](2012/2012.png) |
| 2013 | 7 | +248.75 | $+4,975 | [2013.png](2013/2013.png) |
| 2014 | 5 | +1286.25 | $+25,725 | [2014.png](2014/2014.png) |
| 2015 | 6 | -163.75 | $-3,275 | [2015.png](2015/2015.png) |
| 2016 | 3 | -384.25 | $-7,685 | [2016.png](2016/2016.png) |
| 2017 | 9 | +7898.50 | $+157,970 | [2017.png](2017/2017.png) |
| 2018 | 5 | +1.50 | $+30 | [2018.png](2018/2018.png) |
| 2019 | 4 | +42.50 | $+850 | [2019.png](2019/2019.png) |
| 2020 | 3 | +8646.25 | $+172,925 | [2020.png](2020/2020.png) |
| 2021 | 4 | +16496.50 | $+329,930 | [2021.png](2021/2021.png) |
| 2022 | 1 | +14.00 | $+280 | [2022.png](2022/2022.png) |
| 2023 | 4 | -392.25 | $-7,845 | [2023.png](2023/2023.png) |
| 2024 | 3 | +18811.25 | $+376,225 | [2024.png](2024/2024.png) |
| 2025 | 10 | +1007.25 | $+20,145 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
