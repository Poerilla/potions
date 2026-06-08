# NQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=10; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 1; skipped long add windows: 0; weekly-forced exits: 46.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 121; guard reentries: 93.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 167  ·  Units entered: 343  ·  Win rate: 22.8%  ·  Profit factor: 7.82
Net: +95295.25 pts ($+1,905,905)
Closed-trade max DD: -3114.00 pts ($-62,280)
Mark-to-market max DD: -5102.25 pts ($-102,045)
Worst stack MAE: $-27,965  ·  Avg stack MAE: $-2,976

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 6 | +380.50 | $+7,610 | [2010.png](2010/2010.png) |
| 2011 | 14 | -357.75 | $-7,155 | [2011.png](2011/2011.png) |
| 2012 | 9 | +1387.50 | $+27,750 | [2012.png](2012/2012.png) |
| 2013 | 18 | -217.00 | $-4,340 | [2013.png](2013/2013.png) |
| 2014 | 9 | +1237.75 | $+24,755 | [2014.png](2014/2014.png) |
| 2015 | 22 | -588.00 | $-11,760 | [2015.png](2015/2015.png) |
| 2016 | 11 | -60.00 | $-1,200 | [2016.png](2016/2016.png) |
| 2017 | 8 | +6414.50 | $+128,290 | [2017.png](2017/2017.png) |
| 2018 | 12 | +468.25 | $+9,365 | [2018.png](2018/2018.png) |
| 2019 | 8 | +4144.00 | $+82,880 | [2019.png](2019/2019.png) |
| 2020 | 6 | +31321.00 | $+626,420 | [2020.png](2020/2020.png) |
| 2021 | 9 | +10430.75 | $+208,615 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1647.25 | $-32,945 | [2022.png](2022/2022.png) |
| 2023 | 10 | +9872.50 | $+197,450 | [2023.png](2023/2023.png) |
| 2024 | 8 | +20963.00 | $+419,260 | [2024.png](2024/2024.png) |
| 2025 | 12 | +12090.25 | $+241,805 | [2025.png](2025/2025.png) |
| 2026 | 2 | -544.75 | $-10,895 | [2026.png](2026/2026.png) |
