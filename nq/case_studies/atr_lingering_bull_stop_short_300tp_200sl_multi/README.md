# NQ Lingering Bullish ATR Stop Short Study

Short-only first pass.

Rules:
- Daily ATR Supertrend-style stop: ATR(14) x 3.
- On bullish-to-bearish ATR flip, extend the prior bullish ATR stop for 3 week(s).
- While the ATR trend remains bearish, wait for the first red daily candle that closes below that lingering line.
- After that signal close, place a sell limit at the lingering line on subsequent daily bars.
- Entry size: 1 contract. Target: 300 points. Intraday point stop: 200 points.
- Multiple entries are allowed inside the same lingering-line window, but only after the prior trade has closed; only one trade can be live at a time.
- No close-over-line exit is used; trades close only at target, point stop, or final dataset close.
- If stop and target are both inside the same daily bar, the model uses stop-first ordering.
- Fill-bar ordering is conservative: if the day opens below the sell limit and only later rallies into the limit, same-day target touches are ignored because the low may have printed before the fill.

Causality note: no same-day signal fill is allowed. The sell limit becomes live on the session after the signal candle closes.

## Results

Lingering lines found: 76  ·  Filled trades: 90  ·  Wins: 34  ·  Losses: 56  ·  Win rate: 37.8%  ·  Profit factor: 0.91
Net: -1000.00 pts ($-20,000)
Closed-trade max DD: -4500.00 pts ($-90,000)
Worst MAE: -510.56 pts ($-10,211)  ·  Avg MAE: -181.45 pts ($-3,629)

## Regime / Loss Profile

The longer NQ sample says this is not a broad all-regime short edge. The losses cluster in the older, lower-volatility bull-grind years, while the same logic is much better from 2019 onward.

| Regime | Trades | Net Pts | Win Rate | Read |
|---|---:|---:|---:|---|
| 2010-2014 | 22 | -2400 | 18.2% | Bad: repeated failed bearish flips in grind-up conditions. |
| 2015-2018 | 23 | -1600 | 26.1% | Still bad; drawdown bottomed around the 2017-2018 cluster. |
| 2019-2026 | 45 | +3000 | 53.3% | Matches the MNQ-era behavior and is the only clearly positive regime. |

Lossy years: 2010 (-600), 2012 (-800), 2013 (-800), 2016 (-800), 2017 (-800), 2024 (-500), and 2026 YTD (-600). The old losses are mostly a long sequence of 200-point stops in persistent uptrend regimes; the recent losses are fewer but have much larger MAE because volatility is higher.

The cleanest causal loss profile is signal-day ATR as a percent of close:

| Signal ATR % Filter | Trades | Net Pts | Win Rate | Max DD | Read |
|---|---:|---:|---:|---:|---|
| All trades | 90 | -1000 | 37.8% | -4500 | Weak full-sample result. |
| Signal ATR % < 1.2 | 27 | -3400 | 14.8% | -3700 | Main avoid bucket; low-vol bearish flips usually failed. |
| Signal ATR % >= 1.2 | 63 | +2400 | 47.6% | -1400 | Better, and known before order placement. |
| Signal ATR % >= 2.0 | 16 | +1300 | 56.3% | -600 | Stronger but smaller sample. |
| 2019+ and Signal ATR % >= 1.2 | 40 | +3000 | 55.0% | -900 | Best evidence for a modern high-volatility regime edge. |

Other checks:

- Weekly ATR trend did not separate winners from losers; every filled trade occurred while the mapped weekly ATR trend was already bearish.
- The first attempt was poor before 2019: 44 first attempts, -4300 pts. From 2019 onward, first attempts were +2200 pts.
- Second attempts were mostly a modern-sample feature: 14 total second attempts, +1200 pts. This supports the multi-entry idea, but the sample is small.

Working interpretation: the lingering bullish ATR line is most useful as a short retest level when the bearish break happens in a higher-volatility regime. In quiet bull-grind regimes, the same setup tends to become a failed breakdown and the 200-point stop is repeatedly hit.

## Audit Status

| Status | Count |
|---|---:|
| filled | 90 |
| limit_not_filled | 19 |
| signal_too_late | 1 |

## Exit Reasons

| Exit Reason | Count |
|---|---:|
| Point-Stop | 56 |
| Target | 34 |

## Charts

| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |
|---:|---|---|---:|---:|---|---|
| 1 | 2010-06-27 | Loss | -200.00 | -202.61 | Point-Stop | [001_2010-06-27_loss.png](charts/losers/001_2010-06-27_loss.png) |
| 2 | 2010-08-16 | Loss | -200.00 | -201.69 | Point-Stop | [002_2010-08-16_loss.png](charts/losers/002_2010-08-16_loss.png) |
| 3 | 2010-11-17 | Loss | -200.00 | -202.33 | Point-Stop | [003_2010-11-17_loss.png](charts/losers/003_2010-11-17_loss.png) |
| 4 | 2011-01-31 | Loss | -200.00 | -207.02 | Point-Stop | [004_2011-01-31_loss.png](charts/losers/004_2011-01-31_loss.png) |
| 5 | 2011-02-23 | Win | +300.00 | -105.32 | Target | [005_2011-02-23_win.png](charts/winners/005_2011-02-23_win.png) |
| 6 | 2011-05-17 | Win | +300.00 | -102.57 | Target | [006_2011-05-17_win.png](charts/winners/006_2011-05-17_win.png) |
| 7 | 2011-08-04 | Win | +300.00 | -3.96 | Target | [007_2011-08-04_win.png](charts/winners/007_2011-08-04_win.png) |
| 8 | 2011-10-03 | Loss | -200.00 | -228.93 | Point-Stop | [008_2011-10-03_loss.png](charts/losers/008_2011-10-03_loss.png) |
| 9 | 2011-11-29 | Loss | -200.00 | -205.77 | Point-Stop | [009_2011-11-29_loss.png](charts/losers/009_2011-11-29_loss.png) |
| 10 | 2012-04-11 | Loss | -200.00 | -206.47 | Point-Stop | [010_2012-04-11_loss.png](charts/losers/010_2012-04-11_loss.png) |
| 11 | 2012-07-25 | Loss | -200.00 | -210.72 | Point-Stop | [011_2012-07-25_loss.png](charts/losers/011_2012-07-25_loss.png) |
| 12 | 2012-09-27 | Loss | -200.00 | -201.06 | Point-Stop | [012_2012-09-27_loss.png](charts/losers/012_2012-09-27_loss.png) |
| 13 | 2012-12-31 | Loss | -200.00 | -208.12 | Point-Stop | [013_2012-12-31_loss.png](charts/losers/013_2012-12-31_loss.png) |
| 14 | 2013-04-19 | Loss | -200.00 | -204.51 | Point-Stop | [014_2013-04-19_loss.png](charts/losers/014_2013-04-19_loss.png) |
| 15 | 2013-06-06 | Loss | -200.00 | -203.60 | Point-Stop | [015_2013-06-06_loss.png](charts/losers/015_2013-06-06_loss.png) |
| 16 | 2013-08-22 | Loss | -200.00 | -202.40 | Point-Stop | [016_2013-08-22_loss.png](charts/losers/016_2013-08-22_loss.png) |
| 17 | 2013-10-10 | Loss | -200.00 | -205.38 | Point-Stop | [017_2013-10-10_loss.png](charts/losers/017_2013-10-10_loss.png) |
| 18 | 2014-01-29 | Loss | -200.00 | -206.37 | Point-Stop | [018_2014-01-29_loss.png](charts/losers/018_2014-01-29_loss.png) |
| 19 | 2014-03-31 | Loss | -200.00 | -218.35 | Point-Stop | [019_2014-03-31_loss.png](charts/losers/019_2014-03-31_loss.png) |
| 20 | 2014-08-03 | Loss | -200.00 | -203.15 | Point-Stop | [020_2014-08-03_loss.png](charts/losers/020_2014-08-03_loss.png) |
| 21 | 2014-10-03 | Win | +300.00 | -35.90 | Target | [021_2014-10-03_win.png](charts/winners/021_2014-10-03_win.png) |
| 22 | 2014-12-15 | Loss | -200.00 | -220.00 | Point-Stop | [022_2014-12-15_loss.png](charts/losers/022_2014-12-15_loss.png) |
| 23 | 2015-01-08 | Loss | -200.00 | -201.90 | Point-Stop | [023_2015-01-08_loss.png](charts/losers/023_2015-01-08_loss.png) |
| 24 | 2015-03-16 | Loss | -200.00 | -205.26 | Point-Stop | [024_2015-03-16_loss.png](charts/losers/024_2015-03-16_loss.png) |
| 25 | 2015-03-27 | Loss | -200.00 | -213.68 | Point-Stop | [025_2015-03-27_loss.png](charts/losers/025_2015-03-27_loss.png) |
| 26 | 2015-05-07 | Loss | -200.00 | -220.23 | Point-Stop | [026_2015-05-07_loss.png](charts/losers/026_2015-05-07_loss.png) |
| 27 | 2015-06-30 | Loss | -200.00 | -212.48 | Point-Stop | [027_2015-06-30_loss.png](charts/losers/027_2015-06-30_loss.png) |
| 28 | 2015-08-20 | Win | +300.00 | -5.95 | Target | [028_2015-08-20_win.png](charts/winners/028_2015-08-20_win.png) |
| 29 | 2015-09-29 | Loss | -200.00 | -205.10 | Point-Stop | [029_2015-09-29_loss.png](charts/losers/029_2015-09-29_loss.png) |
| 30 | 2015-11-16 | Win | +300.00 | -198.24 | Target | [030_2015-11-16_win.png](charts/winners/030_2015-11-16_win.png) |
| 31 | 2015-12-14 | Win | +300.00 | -132.19 | Target | [031_2015-12-14_win.png](charts/winners/031_2015-12-14_win.png) |
| 32 | 2016-05-10 | Loss | -200.00 | -223.39 | Point-Stop | [032_2016-05-10_loss.png](charts/losers/032_2016-05-10_loss.png) |
| 33 | 2016-06-20 | Loss | -200.00 | -205.05 | Point-Stop | [033_2016-06-20_loss.png](charts/losers/033_2016-06-20_loss.png) |
| 34 | 2016-09-12 | Loss | -200.00 | -230.58 | Point-Stop | [034_2016-09-12_loss.png](charts/losers/034_2016-09-12_loss.png) |
| 35 | 2016-11-02 | Loss | -200.00 | -201.26 | Point-Stop | [035_2016-11-02_loss.png](charts/losers/035_2016-11-02_loss.png) |
| 36 | 2017-05-18 | Loss | -200.00 | -203.80 | Point-Stop | [036_2017-05-18_loss.png](charts/losers/036_2017-05-18_loss.png) |
| 37 | 2017-06-14 | Loss | -200.00 | -223.09 | Point-Stop | [037_2017-06-14_loss.png](charts/losers/037_2017-06-14_loss.png) |
| 38 | 2017-08-11 | Loss | -200.00 | -205.48 | Point-Stop | [038_2017-08-11_loss.png](charts/losers/038_2017-08-11_loss.png) |
| 39 | 2017-12-05 | Loss | -200.00 | -214.72 | Point-Stop | [039_2017-12-05_loss.png](charts/losers/039_2017-12-05_loss.png) |
| 40 | 2018-03-27 | Win | +300.00 | -31.51 | Target | [040_2018-03-27_win.png](charts/winners/040_2018-03-27_win.png) |
| 41 | 2018-06-26 | Loss | -200.00 | -253.46 | Point-Stop | [041_2018-06-26_loss.png](charts/losers/041_2018-06-26_loss.png) |
| 42 | 2018-09-07 | Loss | -200.00 | -204.18 | Point-Stop | [042_2018-09-07_loss.png](charts/losers/042_2018-09-07_loss.png) |
| 43 | 2018-10-07 | Win | +300.00 | -5.11 | Target | [043_2018-10-07_win.png](charts/winners/043_2018-10-07_win.png) |
| 44 | 2018-12-10 | Loss | -200.00 | -223.58 | Point-Stop | [044_2018-12-10_loss.png](charts/losers/044_2018-12-10_loss.png) |
| 45 | 2018-12-17 | Win | +300.00 | -7.58 | Target | [045_2018-12-17_win.png](charts/winners/045_2018-12-17_win.png) |
| 46 | 2019-05-10 | Win | +300.00 | -11.02 | Target | [046_2019-05-10_win.png](charts/winners/046_2019-05-10_win.png) |
| 47 | 2019-08-13 | Win | +300.00 | -18.30 | Target | [047_2019-08-13_win.png](charts/winners/047_2019-08-13_win.png) |
| 48 | 2019-08-21 | Win | +300.00 | -11.05 | Target | [048_2019-08-21_win.png](charts/winners/048_2019-08-21_win.png) |
| 49 | 2019-10-03 | Loss | -200.00 | -218.38 | Point-Stop | [049_2019-10-03_loss.png](charts/losers/049_2019-10-03_loss.png) |
| 50 | 2020-09-04 | Win | +300.00 | -87.16 | Target | [050_2020-09-04_win.png](charts/winners/050_2020-09-04_win.png) |
| 51 | 2020-10-29 | Win | +300.00 | -106.11 | Target | [051_2020-10-29_win.png](charts/winners/051_2020-10-29_win.png) |
| 52 | 2021-02-01 | Loss | -200.00 | -328.54 | Point-Stop | [052_2021-02-01_loss.png](charts/losers/052_2021-02-01_loss.png) |
| 53 | 2021-02-23 | Win | +300.00 | -37.13 | Target | [053_2021-02-23_win.png](charts/winners/053_2021-02-23_win.png) |
| 54 | 2021-03-01 | Win | +300.00 | -25.13 | Target | [054_2021-03-01_win.png](charts/winners/054_2021-03-01_win.png) |
| 55 | 2021-05-14 | Win | +300.00 | -26.80 | Target | [055_2021-05-14_win.png](charts/winners/055_2021-05-14_win.png) |
| 56 | 2021-05-24 | Loss | -200.00 | -264.30 | Point-Stop | [056_2021-05-24_loss.png](charts/losers/056_2021-05-24_loss.png) |
| 57 | 2021-09-19 | Win | +300.00 | -49.62 | Target | [057_2021-09-19_win.png](charts/winners/057_2021-09-19_win.png) |
| 58 | 2021-09-23 | Win | +300.00 | -110.62 | Target | [058_2021-09-23_win.png](charts/winners/058_2021-09-23_win.png) |
| 59 | 2021-11-28 | Loss | -200.00 | -331.85 | Point-Stop | [059_2021-11-28_loss.png](charts/losers/059_2021-11-28_loss.png) |
| 60 | 2021-12-03 | Win | +300.00 | -12.60 | Target | [060_2021-12-03_win.png](charts/winners/060_2021-12-03_win.png) |
| 61 | 2021-12-14 | Loss | -200.00 | -228.60 | Point-Stop | [061_2021-12-14_loss.png](charts/losers/061_2021-12-14_loss.png) |
| 62 | 2022-01-11 | Loss | -200.00 | -289.46 | Point-Stop | [062_2022-01-11_loss.png](charts/losers/062_2022-01-11_loss.png) |
| 63 | 2022-04-12 | Win | +300.00 | -199.84 | Target | [063_2022-04-12_win.png](charts/winners/063_2022-04-12_win.png) |
| 64 | 2022-06-15 | Win | +300.00 | -91.83 | Target | [064_2022-06-15_win.png](charts/winners/064_2022-06-15_win.png) |
| 65 | 2022-06-22 | Loss | -200.00 | -446.08 | Point-Stop | [065_2022-06-22_loss.png](charts/losers/065_2022-06-22_loss.png) |
| 66 | 2022-06-29 | Win | +300.00 | -46.58 | Target | [066_2022-06-29_win.png](charts/winners/066_2022-06-29_win.png) |
| 67 | 2022-09-12 | Win | +300.00 | -140.09 | Target | [067_2022-09-12_win.png](charts/winners/067_2022-09-12_win.png) |
| 68 | 2022-12-21 | Win | +300.00 | -101.75 | Target | [068_2022-12-21_win.png](charts/winners/068_2022-12-21_win.png) |
| 69 | 2023-01-09 | Loss | -200.00 | -291.75 | Point-Stop | [069_2023-01-09_loss.png](charts/losers/069_2023-01-09_loss.png) |
| 70 | 2023-03-12 | Loss | -200.00 | -280.73 | Point-Stop | [070_2023-03-12_loss.png](charts/losers/070_2023-03-12_loss.png) |
| 71 | 2023-08-06 | Win | +300.00 | -113.39 | Target | [071_2023-08-06_win.png](charts/winners/071_2023-08-06_win.png) |
| 72 | 2023-08-24 | Win | +300.00 | -33.64 | Target | [072_2023-08-24_win.png](charts/winners/072_2023-08-24_win.png) |
| 73 | 2023-09-22 | Win | +300.00 | -14.75 | Target | [073_2023-09-22_win.png](charts/winners/073_2023-09-22_win.png) |
| 74 | 2023-10-02 | Win | +300.00 | -33.25 | Target | [074_2023-10-02_win.png](charts/winners/074_2023-10-02_win.png) |
| 75 | 2023-10-06 | Loss | -200.00 | -370.75 | Point-Stop | [075_2023-10-06_loss.png](charts/losers/075_2023-10-06_loss.png) |
| 76 | 2023-11-01 | Loss | -200.00 | -387.47 | Point-Stop | [076_2023-11-01_loss.png](charts/losers/076_2023-11-01_loss.png) |
| 77 | 2024-01-08 | Loss | -200.00 | -227.89 | Point-Stop | [077_2024-01-08_loss.png](charts/losers/077_2024-01-08_loss.png) |
| 78 | 2024-04-16 | Win | +300.00 | -32.23 | Target | [078_2024-04-16_win.png](charts/winners/078_2024-04-16_win.png) |
| 79 | 2024-05-03 | Loss | -200.00 | -245.48 | Point-Stop | [079_2024-05-03_loss.png](charts/losers/079_2024-05-03_loss.png) |
| 80 | 2024-09-10 | Loss | -200.00 | -509.59 | Point-Stop | [080_2024-09-10_loss.png](charts/losers/080_2024-09-10_loss.png) |
| 81 | 2024-12-19 | Loss | -200.00 | -216.62 | Point-Stop | [081_2024-12-19_loss.png](charts/losers/081_2024-12-19_loss.png) |
| 82 | 2025-01-06 | Loss | -200.00 | -301.12 | Point-Stop | [082_2025-01-06_loss.png](charts/losers/082_2025-01-06_loss.png) |
| 83 | 2025-02-26 | Win | +300.00 | -75.66 | Target | [083_2025-02-26_win.png](charts/winners/083_2025-02-26_win.png) |
| 84 | 2025-08-03 | Loss | -200.00 | -443.82 | Point-Stop | [084_2025-08-03_loss.png](charts/losers/084_2025-08-03_loss.png) |
| 85 | 2025-10-12 | Loss | -200.00 | -248.31 | Point-Stop | [085_2025-10-12_loss.png](charts/losers/085_2025-10-12_loss.png) |
| 86 | 2025-11-14 | Win | +300.00 | -185.13 | Target | [086_2025-11-14_win.png](charts/winners/086_2025-11-14_win.png) |
| 87 | 2025-11-20 | Win | +300.00 | -133.88 | Target | [087_2025-11-20_win.png](charts/winners/087_2025-11-20_win.png) |
| 88 | 2026-01-21 | Loss | -200.00 | -510.56 | Point-Stop | [088_2026-01-21_loss.png](charts/losers/088_2026-01-21_loss.png) |
| 89 | 2026-02-08 | Loss | -200.00 | -205.84 | Point-Stop | [089_2026-02-08_loss.png](charts/losers/089_2026-02-08_loss.png) |
| 90 | 2026-02-25 | Loss | -200.00 | -271.84 | Point-Stop | [090_2026-02-25_loss.png](charts/losers/090_2026-02-25_loss.png) |
