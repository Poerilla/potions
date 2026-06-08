# NQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 19.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 70. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 54; guard reentries: 37.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 73  ·  Units entered: 178  ·  Win rate: 21.9%  ·  Profit factor: 11.05
Net: +49550.00 pts ($+991,000)
Closed-trade max DD: -1244.00 pts ($-24,880)
Mark-to-market max DD: -6410.00 pts ($-128,200)
Worst stack MAE: $-32,905  ·  Avg stack MAE: $-2,770

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 0 | +0.00 | $+0 | [2010.png](2010/2010.png) |
| 2011 | 0 | +0.00 | $+0 | [2011.png](2011/2011.png) |
| 2012 | 3 | -35.50 | $-710 | [2012.png](2012/2012.png) |
| 2013 | 9 | -91.00 | $-1,820 | [2013.png](2013/2013.png) |
| 2014 | 6 | +1060.25 | $+21,205 | [2014.png](2014/2014.png) |
| 2015 | 9 | -329.00 | $-6,580 | [2015.png](2015/2015.png) |
| 2016 | 6 | -210.50 | $-4,210 | [2016.png](2016/2016.png) |
| 2017 | 8 | +7720.25 | $+154,405 | [2017.png](2017/2017.png) |
| 2018 | 5 | -208.75 | $-4,175 | [2018.png](2018/2018.png) |
| 2019 | 7 | -328.00 | $-6,560 | [2019.png](2019/2019.png) |
| 2020 | 4 | +8302.50 | $+166,050 | [2020.png](2020/2020.png) |
| 2021 | 5 | +15069.25 | $+301,385 | [2021.png](2021/2021.png) |
| 2022 | 0 | +0.00 | $+0 | [2022.png](2022/2022.png) |
| 2023 | 5 | -415.75 | $-8,315 | [2023.png](2023/2023.png) |
| 2024 | 4 | +17856.50 | $+357,130 | [2024.png](2024/2024.png) |
| 2025 | 8 | +1159.75 | $+23,195 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
