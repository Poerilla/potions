# NQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=5; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 50.
Prior bearish stop guard: exit-reclaim; guard exits: 51; guard reentries: 26.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 101  ·  Units entered: 235  ·  Win rate: 33.7%  ·  Profit factor: 9.52
Net: +79697.00 pts ($+1,593,940)
Closed-trade max DD: -2790.50 pts ($-55,810)
Mark-to-market max DD: -4006.25 pts ($-80,125)
Worst stack MAE: $-27,865  ·  Avg stack MAE: $-3,934

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 5 | +249.50 | $+4,990 | [2010.png](2010/2010.png) |
| 2011 | 8 | -172.00 | $-3,440 | [2011.png](2011/2011.png) |
| 2012 | 6 | +1118.00 | $+22,360 | [2012.png](2012/2012.png) |
| 2013 | 6 | +122.25 | $+2,445 | [2013.png](2013/2013.png) |
| 2014 | 7 | +1087.75 | $+21,755 | [2014.png](2014/2014.png) |
| 2015 | 10 | -253.50 | $-5,070 | [2015.png](2015/2015.png) |
| 2016 | 8 | -233.50 | $-4,670 | [2016.png](2016/2016.png) |
| 2017 | 6 | +4511.75 | $+90,235 | [2017.png](2017/2017.png) |
| 2018 | 9 | +423.00 | $+8,460 | [2018.png](2018/2018.png) |
| 2019 | 5 | +3969.00 | $+79,380 | [2019.png](2019/2019.png) |
| 2020 | 5 | +21582.25 | $+431,645 | [2020.png](2020/2020.png) |
| 2021 | 6 | +9392.25 | $+187,845 | [2021.png](2021/2021.png) |
| 2022 | 7 | -1692.50 | $-33,850 | [2022.png](2022/2022.png) |
| 2023 | 5 | +10106.75 | $+202,135 | [2023.png](2023/2023.png) |
| 2024 | 6 | +19858.25 | $+397,165 | [2024.png](2024/2024.png) |
| 2025 | 7 | +9828.50 | $+196,570 | [2025.png](2025/2025.png) |
| 2026 | 1 | -200.75 | $-4,015 | [2026.png](2026/2026.png) |
