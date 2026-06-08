# NQ ATR Supertrend DCA Study

Rules: daily Supertrend-style ATR(14) x 3; sides=long; enter next daily open after an enabled ATR trend flip; start with 1 contract; add 1 contract every 2 eligible Friday(s) at 15:50 ET while the previous completed ATR trend still agrees and price is on the correct side of the previous ATR stop; max contracts per stack=5; exit/reverse entire stack next daily open after an opposite ATR flip.
Weekly long filter: flat-when-bearish using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 75.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 75  ·  Units entered: 253  ·  Win rate: 50.7%  ·  Profit factor: 7.86
Net: +93049.75 pts ($+1,860,995)
Closed-trade max DD: -4395.25 pts ($-87,905)
Mark-to-market max DD: -5352.75 pts ($-107,055)
Worst stack MAE: $-33,550  ·  Avg stack MAE: $-7,717

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 3 | +485.50 | $+9,710 | [2010.png](2010/2010.png) |
| 2011 | 7 | -167.00 | $-3,340 | [2011.png](2011/2011.png) |
| 2012 | 4 | +2036.25 | $+40,725 | [2012.png](2012/2012.png) |
| 2013 | 5 | +227.75 | $+4,555 | [2013.png](2013/2013.png) |
| 2014 | 6 | +1573.25 | $+31,465 | [2014.png](2014/2014.png) |
| 2015 | 9 | -722.00 | $-14,440 | [2015.png](2015/2015.png) |
| 2016 | 5 | +296.00 | $+5,920 | [2016.png](2016/2016.png) |
| 2017 | 5 | +5976.75 | $+119,535 | [2017.png](2017/2017.png) |
| 2018 | 6 | +1976.50 | $+39,530 | [2018.png](2018/2018.png) |
| 2019 | 4 | +3849.25 | $+76,985 | [2019.png](2019/2019.png) |
| 2020 | 4 | +21480.00 | $+429,600 | [2020.png](2020/2020.png) |
| 2021 | 6 | +11102.25 | $+222,045 | [2021.png](2021/2021.png) |
| 2022 | 5 | -3388.25 | $-67,765 | [2022.png](2022/2022.png) |
| 2023 | 5 | +9606.25 | $+192,125 | [2023.png](2023/2023.png) |
| 2024 | 5 | +21495.50 | $+429,910 | [2024.png](2024/2024.png) |
| 2025 | 5 | +18781.50 | $+375,630 | [2025.png](2025/2025.png) |
| 2026 | 2 | -1559.75 | $-31,195 | [2026.png](2026/2026.png) |
