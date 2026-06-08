# ES ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 5.
Yearly ORB first-entry filter: none; Jan-Mar range, from April onward long starts require a prior daily close above the yearly ORB high; skipped long starts/restarts: 0. Adds and exits are unchanged by this filter.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 37; guard reentries: 34.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 43  ·  Units entered: 142  ·  Win rate: 11.6%  ·  Profit factor: 4.74
Net: +25038.50 pts ($+125,192)
Closed-trade max DD: -2213.25 pts ($-11,066)
Mark-to-market max DD: -6667.25 pts ($-33,336)
Worst stack MAE: $-10,456  ·  Avg stack MAE: $-1,194

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 0 | +0.00 | $+0 | [2010.png](2010/2010.png) |
| 2011 | 0 | +0.00 | $+0 | [2011.png](2011/2011.png) |
| 2012 | 6 | -663.00 | $-3,315 | [2012.png](2012/2012.png) |
| 2013 | 0 | +0.00 | $+0 | [2013.png](2013/2013.png) |
| 2014 | 4 | +4953.00 | $+24,765 | [2014.png](2014/2014.png) |
| 2015 | 6 | -1249.00 | $-6,245 | [2015.png](2015/2015.png) |
| 2016 | 8 | -176.00 | $-880 | [2016.png](2016/2016.png) |
| 2017 | 0 | +0.00 | $+0 | [2017.png](2017/2017.png) |
| 2018 | 5 | +3952.50 | $+19,762 | [2018.png](2018/2018.png) |
| 2019 | 5 | -993.50 | $-4,968 | [2019.png](2019/2019.png) |
| 2020 | 2 | -443.25 | $-2,216 | [2020.png](2020/2020.png) |
| 2021 | 0 | +0.00 | $+0 | [2021.png](2021/2021.png) |
| 2022 | 1 | +11642.50 | $+58,212 | [2022.png](2022/2022.png) |
| 2023 | 7 | -2040.75 | $-10,204 | [2023.png](2023/2023.png) |
| 2024 | 1 | +0.00 | $+0 | [2024.png](2024/2024.png) |
| 2025 | 5 | +7397.00 | $+36,985 | [2025.png](2025/2025.png) |
| 2026 | 1 | +2659.00 | $+13,295 | [2026.png](2026/2026.png) |
