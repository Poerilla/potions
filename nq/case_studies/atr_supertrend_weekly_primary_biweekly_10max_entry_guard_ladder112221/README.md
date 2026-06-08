# NQ ATR Supertrend DCA Study

Signal timeframe: weekly.
Rules: weekly Supertrend-style ATR(14) x 3; sides=long; enter at the next available daily open after an enabled weekly ATR trend flip; scale every 2 eligible Friday(s) at 15:50 ET while the completed weekly ATR trend still agrees and price is on the correct side of the completed weekly ATR stop; max contracts per stack=10; exit the entire stack at the next available daily open after an opposite weekly ATR flip.
Size schedule: 1,1,2,2,2; after the explicit schedule is exhausted, add 1 contract per eligible add event until max contracts.
Weekly long filter: primary weekly signal using weekly Supertrend-style ATR(14) x 3; skipped long entries/reversals: 0; skipped long add windows: 0; weekly-forced exits: 54.
Prior bearish stop guard: none; guard exits: 0; guard reentries: 0.
Initial entry price guard: exit-reclaim; guard exits: 69; guard reentries: 48.

Important modeling note: entries/exits use daily next-open prices. Friday adds use 1-minute 15:50 ET bars when available. MAE is open-stack heat estimated from daily lows after units are live.
Chart note: solid cyan/orange lines are the daily ATR stop. Dashed lime/orange lines are the causal completed-week ATR stop when weekly overlay is enabled. Dotted horizontal segments extend a broken ATR stop for 3 week(s) after the reversal close.

Trades/stacks: 123  ·  Units entered: 401  ·  Win rate: 31.7%  ·  Profit factor: 14.34
Net: +152242.00 pts ($+3,044,840)
Closed-trade max DD: -3044.25 pts ($-60,885)
Mark-to-market max DD: -6410.00 pts ($-128,200)
Worst stack MAE: $-32,030  ·  Avg stack MAE: $-4,087

## Year Charts

| Year | Active Stacks | Exit Pts | Exit $ | Chart |
|---:|---:|---:|---:|---|
| 2010 | 4 | +703.50 | $+14,070 | [2010.png](2010/2010.png) |
| 2011 | 12 | -405.25 | $-8,105 | [2011.png](2011/2011.png) |
| 2012 | 8 | +2088.25 | $+41,765 | [2012.png](2012/2012.png) |
| 2013 | 7 | +248.75 | $+4,975 | [2013.png](2013/2013.png) |
| 2014 | 7 | +2022.75 | $+40,455 | [2014.png](2014/2014.png) |
| 2015 | 16 | -318.00 | $-6,360 | [2015.png](2015/2015.png) |
| 2016 | 7 | -209.00 | $-4,180 | [2016.png](2016/2016.png) |
| 2017 | 9 | +7898.50 | $+157,970 | [2017.png](2017/2017.png) |
| 2018 | 8 | +1246.75 | $+24,935 | [2018.png](2018/2018.png) |
| 2019 | 5 | +6711.75 | $+134,235 | [2019.png](2019/2019.png) |
| 2020 | 4 | +38911.75 | $+778,235 | [2020.png](2020/2020.png) |
| 2021 | 6 | +16318.50 | $+326,370 | [2021.png](2021/2021.png) |
| 2022 | 10 | -1622.75 | $-32,455 | [2022.png](2022/2022.png) |
| 2023 | 6 | +20116.25 | $+402,325 | [2023.png](2023/2023.png) |
| 2024 | 6 | +32949.50 | $+658,990 | [2024.png](2024/2024.png) |
| 2025 | 14 | +26240.50 | $+524,810 | [2025.png](2025/2025.png) |
| 2026 | 3 | -659.75 | $-13,195 | [2026.png](2026/2026.png) |
