# NQ ATR Supertrend DCA Study

Signal timeframe: daily.
Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled daily ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed daily ATR trend still agrees and price is on the correct side of the completed daily ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite daily ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 1; skipped long add windows: 0; weekly-forced exits: 46.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 121; guard reentries: 93.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 167  ·  Units entered: 411  ·  Win rate: 22.2%  ·  Profit factor: 9.20
Net: +127840.50 pts ($+2,556,810)
Closed-trade max DD: -3929.00 pts ($-78,580)
Mark-to-market max DD: -6410.00 pts ($-128,200)
Worst stack MAE: $-42,440  ·  Avg stack MAE: $-3,533

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 6 | +539.25 | $+10,785 | [2010.png](2010/2010.png) |
| 2011 | 14 | -534.50 | $-10,690 | [2011.png](2011/2011.png) |
| 2012 | 9 | +1967.75 | $+39,355 | [2012.png](2012/2012.png) |
| 2013 | 18 | -270.75 | $-5,415 | [2013.png](2013/2013.png) |
| 2014 | 9 | +1462.50 | $+29,250 | [2014.png](2014/2014.png) |
| 2015 | 22 | -567.00 | $-11,340 | [2015.png](2015/2015.png) |
| 2016 | 11 | -353.50 | $-7,070 | [2016.png](2016/2016.png) |
| 2017 | 8 | +7720.25 | $+154,405 | [2017.png](2017/2017.png) |
| 2018 | 12 | +216.50 | $+4,330 | [2018.png](2018/2018.png) |
| 2019 | 8 | +6057.25 | $+121,145 | [2019.png](2019/2019.png) |
| 2020 | 6 | +38138.50 | $+762,770 | [2020.png](2020/2020.png) |
| 2021 | 9 | +13831.50 | $+276,630 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1769.00 | $-35,380 | [2022.png](2022/2022.png) |
| 2023 | 10 | +15784.25 | $+315,685 | [2023.png](2023/2023.png) |
| 2024 | 8 | +28485.00 | $+569,700 | [2024.png](2024/2024.png) |
| 2025 | 12 | +17677.25 | $+353,545 | [2025.png](2025/2025.png) |
| 2026 | 2 | -544.75 | $-10,895 | [2026.png](2026/2026.png) |
