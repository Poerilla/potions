# NQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 3, then 1 per add; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 19.
Yearly ORB first-entry filter: long-breakout; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 70. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 54; guard reentries: 37.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 73  ·  Units entered: 292  ·  Win rate: 26.0%  ·  Profit factor: 5.30
Net: +55766.50 pts ($+1,115,330)
Closed-trade max DD: -2784.75 pts ($-55,695)
Mark-to-market max DD: -5608.75 pts ($-112,175)
Worst stack MAE: $-54,705  ·  Avg stack MAE: $-5,679

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 0 | +0.00 | $+0 | [2010.png](2010/2010.png) |
| 2011 | 0 | +0.00 | $+0 | [2011.png](2011/2011.png) |
| 2012 | 3 | -90.50 | $-1,810 | [2012.png](2012/2012.png) |
| 2013 | 9 | +193.75 | $+3,875 | [2013.png](2013/2013.png) |
| 2014 | 6 | +1829.50 | $+36,590 | [2014.png](2014/2014.png) |
| 2015 | 9 | -904.00 | $-18,080 | [2015.png](2015/2015.png) |
| 2016 | 6 | -458.50 | $-9,170 | [2016.png](2016/2016.png) |
| 2017 | 8 | +8467.75 | $+169,355 | [2017.png](2017/2017.png) |
| 2018 | 5 | -265.50 | $-5,310 | [2018.png](2018/2018.png) |
| 2019 | 7 | -243.75 | $-4,875 | [2019.png](2019/2019.png) |
| 2020 | 4 | +8128.50 | $+162,570 | [2020.png](2020/2020.png) |
| 2021 | 5 | +19244.00 | $+384,880 | [2021.png](2021/2021.png) |
| 2022 | 0 | +0.00 | $+0 | [2022.png](2022/2022.png) |
| 2023 | 5 | -1247.25 | $-24,945 | [2023.png](2023/2023.png) |
| 2024 | 4 | +20197.25 | $+403,945 | [2024.png](2024/2024.png) |
| 2025 | 8 | +915.25 | $+18,305 | [2025.png](2025/2025.png) |
| 2026 | 0 | +0.00 | $+0 | [2026.png](2026/2026.png) |
