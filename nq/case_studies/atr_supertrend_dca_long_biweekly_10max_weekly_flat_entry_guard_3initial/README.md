# NQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 3 contract(s); add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=10; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 1; skipped long add windows: 0; weekly-forced exits: 46.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 121; guard reentries: 93.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 167  ·  Units entered: 669  ·  Win rate: 25.7%  ·  Profit factor: 5.02
Net: +136999.25 pts ($+2,739,985)
Closed-trade max DD: -6315.50 pts ($-126,310)
Mark-to-market max DD: -7791.75 pts ($-155,835)
Worst stack MAE: $-83,595  ·  Avg stack MAE: $-6,720

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 6 | +664.00 | $+13,280 | [2010.png](2010/2010.png) |
| 2011 | 14 | -493.75 | $-9,875 | [2011.png](2011/2011.png) |
| 2012 | 9 | +2013.50 | $+40,270 | [2012.png](2012/2012.png) |
| 2013 | 18 | -306.00 | $-6,120 | [2013.png](2013/2013.png) |
| 2014 | 9 | +2864.75 | $+57,295 | [2014.png](2014/2014.png) |
| 2015 | 22 | -1528.00 | $-30,560 | [2015.png](2015/2015.png) |
| 2016 | 11 | +363.50 | $+7,270 | [2016.png](2016/2016.png) |
| 2017 | 8 | +8467.75 | $+169,355 | [2017.png](2017/2017.png) |
| 2018 | 12 | +1296.25 | $+25,925 | [2018.png](2018/2018.png) |
| 2019 | 8 | +6680.75 | $+133,615 | [2019.png](2019/2019.png) |
| 2020 | 6 | +38791.50 | $+775,830 | [2020.png](2020/2020.png) |
| 2021 | 9 | +18186.25 | $+363,725 | [2021.png](2021/2021.png) |
| 2022 | 10 | -4547.25 | $-90,945 | [2022.png](2022/2022.png) |
| 2023 | 10 | +14555.50 | $+291,110 | [2023.png](2023/2023.png) |
| 2024 | 8 | +34769.00 | $+695,380 | [2024.png](2024/2024.png) |
| 2025 | 12 | +16855.75 | $+337,115 | [2025.png](2025/2025.png) |
| 2026 | 2 | -1634.25 | $-32,685 | [2026.png](2026/2026.png) |
