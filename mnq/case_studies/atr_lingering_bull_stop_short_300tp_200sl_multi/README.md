# MNQ Lingering Bullish ATR Stop Short Study

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

Lingering lines found: 31  ·  Filled trades: 45  ·  Wins: 24  ·  Losses: 21  ·  Win rate: 53.3%  ·  Profit factor: 1.71
Net: +3000.00 pts ($+6,000)
Closed-trade max DD: -1200.00 pts ($-2,400)
Worst MAE: -509.66 pts ($-1,019)  ·  Avg MAE: -181.78 pts ($-364)

## NQ Longer-Sample Regime Check

The matching NQ run is negative across the full 2010-2026 sample, but the damage is concentrated before the MNQ-era sample begins:

| Regime | NQ Trades | NQ Net Pts | Win Rate | Read |
|---|---:|---:|---:|---|
| 2010-2014 | 22 | -2400 | 18.2% | Bad low-volatility bull-grind regime. |
| 2015-2018 | 23 | -1600 | 26.1% | Still bad; drawdown bottomed near 2017-2018. |
| 2019-2026 | 45 | +3000 | 53.3% | Matches this MNQ result. |

The most useful causal filter from the NQ sample is signal-day ATR as a percent of close, known after the signal candle closes and before the sell limit is live:

| NQ Signal ATR % Filter | Trades | Net Pts | Win Rate | Max DD |
|---|---:|---:|---:|---:|
| < 1.2 | 27 | -3400 | 14.8% | -3700 |
| >= 1.2 | 63 | +2400 | 47.6% | -1400 |
| 2019+ and >= 1.2 | 40 | +3000 | 55.0% | -900 |

Working interpretation: this is a modern/high-volatility short retest behavior, not an all-regime edge. Avoiding low-volatility bearish flips is the first filter worth testing.

## Audit Status

| Status | Count |
|---|---:|
| filled | 45 |
| limit_not_filled | 13 |
| signal_too_late | 1 |

## Exit Reasons

| Exit Reason | Count |
|---|---:|
| Point-Stop | 21 |
| Target | 24 |

## Charts

| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |
|---:|---|---|---:|---:|---|---|
| 1 | 2019-05-16 | Win | +300.00 | -63.62 | Target | [001_2019-05-16_win.png](charts/winners/001_2019-05-16_win.png) |
| 2 | 2019-08-13 | Win | +300.00 | -18.58 | Target | [002_2019-08-13_win.png](charts/winners/002_2019-08-13_win.png) |
| 3 | 2019-08-21 | Win | +300.00 | -11.58 | Target | [003_2019-08-21_win.png](charts/winners/003_2019-08-21_win.png) |
| 4 | 2019-10-03 | Loss | -200.00 | -220.93 | Point-Stop | [004_2019-10-03_loss.png](charts/losers/004_2019-10-03_loss.png) |
| 5 | 2020-09-04 | Win | +300.00 | -88.55 | Target | [005_2020-09-04_win.png](charts/winners/005_2020-09-04_win.png) |
| 6 | 2020-10-29 | Win | +300.00 | -106.40 | Target | [006_2020-10-29_win.png](charts/winners/006_2020-10-29_win.png) |
| 7 | 2021-02-01 | Loss | -200.00 | -329.45 | Point-Stop | [007_2021-02-01_loss.png](charts/losers/007_2021-02-01_loss.png) |
| 8 | 2021-02-23 | Win | +300.00 | -35.81 | Target | [008_2021-02-23_win.png](charts/winners/008_2021-02-23_win.png) |
| 9 | 2021-03-01 | Win | +300.00 | -24.81 | Target | [009_2021-03-01_win.png](charts/winners/009_2021-03-01_win.png) |
| 10 | 2021-05-14 | Win | +300.00 | -29.57 | Target | [010_2021-05-14_win.png](charts/winners/010_2021-05-14_win.png) |
| 11 | 2021-05-24 | Loss | -200.00 | -263.32 | Point-Stop | [011_2021-05-24_loss.png](charts/losers/011_2021-05-24_loss.png) |
| 12 | 2021-09-19 | Win | +300.00 | -50.94 | Target | [012_2021-09-19_win.png](charts/winners/012_2021-09-19_win.png) |
| 13 | 2021-09-23 | Win | +300.00 | -112.44 | Target | [013_2021-09-23_win.png](charts/winners/013_2021-09-23_win.png) |
| 14 | 2021-11-28 | Loss | -200.00 | -331.80 | Point-Stop | [014_2021-11-28_loss.png](charts/losers/014_2021-11-28_loss.png) |
| 15 | 2021-12-03 | Win | +300.00 | -12.55 | Target | [015_2021-12-03_win.png](charts/winners/015_2021-12-03_win.png) |
| 16 | 2021-12-14 | Loss | -200.00 | -228.80 | Point-Stop | [016_2021-12-14_loss.png](charts/losers/016_2021-12-14_loss.png) |
| 17 | 2022-01-11 | Loss | -200.00 | -290.45 | Point-Stop | [017_2022-01-11_loss.png](charts/losers/017_2022-01-11_loss.png) |
| 18 | 2022-04-12 | Win | +300.00 | -199.73 | Target | [018_2022-04-12_win.png](charts/winners/018_2022-04-12_win.png) |
| 19 | 2022-06-15 | Win | +300.00 | -92.64 | Target | [019_2022-06-15_win.png](charts/winners/019_2022-06-15_win.png) |
| 20 | 2022-06-22 | Loss | -200.00 | -447.39 | Point-Stop | [020_2022-06-22_loss.png](charts/losers/020_2022-06-22_loss.png) |
| 21 | 2022-06-29 | Win | +300.00 | -47.39 | Target | [021_2022-06-29_win.png](charts/winners/021_2022-06-29_win.png) |
| 22 | 2022-09-12 | Win | +300.00 | -133.23 | Target | [022_2022-09-12_win.png](charts/winners/022_2022-09-12_win.png) |
| 23 | 2022-12-21 | Win | +300.00 | -104.32 | Target | [023_2022-12-21_win.png](charts/winners/023_2022-12-21_win.png) |
| 24 | 2023-01-09 | Loss | -200.00 | -294.57 | Point-Stop | [024_2023-01-09_loss.png](charts/losers/024_2023-01-09_loss.png) |
| 25 | 2023-03-12 | Loss | -200.00 | -221.82 | Point-Stop | [025_2023-03-12_loss.png](charts/losers/025_2023-03-12_loss.png) |
| 26 | 2023-08-06 | Win | +300.00 | -116.94 | Target | [026_2023-08-06_win.png](charts/winners/026_2023-08-06_win.png) |
| 27 | 2023-08-24 | Win | +300.00 | -36.69 | Target | [027_2023-08-24_win.png](charts/winners/027_2023-08-24_win.png) |
| 28 | 2023-09-22 | Win | +300.00 | -14.65 | Target | [028_2023-09-22_win.png](charts/winners/028_2023-09-22_win.png) |
| 29 | 2023-10-02 | Win | +300.00 | -33.65 | Target | [029_2023-10-02_win.png](charts/winners/029_2023-10-02_win.png) |
| 30 | 2023-10-06 | Loss | -200.00 | -200.15 | Point-Stop | [030_2023-10-06_loss.png](charts/losers/030_2023-10-06_loss.png) |
| 31 | 2023-11-01 | Loss | -200.00 | -386.28 | Point-Stop | [031_2023-11-01_loss.png](charts/losers/031_2023-11-01_loss.png) |
| 32 | 2024-01-08 | Loss | -200.00 | -227.22 | Point-Stop | [032_2024-01-08_loss.png](charts/losers/032_2024-01-08_loss.png) |
| 33 | 2024-04-16 | Win | +300.00 | -34.10 | Target | [033_2024-04-16_win.png](charts/winners/033_2024-04-16_win.png) |
| 34 | 2024-05-03 | Loss | -200.00 | -247.85 | Point-Stop | [034_2024-05-03_loss.png](charts/losers/034_2024-05-03_loss.png) |
| 35 | 2024-09-10 | Loss | -200.00 | -509.66 | Point-Stop | [035_2024-09-10_loss.png](charts/losers/035_2024-09-10_loss.png) |
| 36 | 2024-12-19 | Loss | -200.00 | -217.82 | Point-Stop | [036_2024-12-19_loss.png](charts/losers/036_2024-12-19_loss.png) |
| 37 | 2025-01-06 | Loss | -200.00 | -302.32 | Point-Stop | [037_2025-01-06_loss.png](charts/losers/037_2025-01-06_loss.png) |
| 38 | 2025-02-26 | Win | +300.00 | -77.92 | Target | [038_2025-02-26_win.png](charts/winners/038_2025-02-26_win.png) |
| 39 | 2025-08-03 | Loss | -200.00 | -447.50 | Point-Stop | [039_2025-08-03_loss.png](charts/losers/039_2025-08-03_loss.png) |
| 40 | 2025-10-12 | Loss | -200.00 | -248.17 | Point-Stop | [040_2025-10-12_loss.png](charts/losers/040_2025-10-12_loss.png) |
| 41 | 2025-11-14 | Win | +300.00 | -192.73 | Target | [041_2025-11-14_win.png](charts/winners/041_2025-11-14_win.png) |
| 42 | 2025-11-20 | Win | +300.00 | -140.73 | Target | [042_2025-11-20_win.png](charts/winners/042_2025-11-20_win.png) |
| 43 | 2026-01-21 | Loss | -200.00 | -509.48 | Point-Stop | [043_2026-01-21_loss.png](charts/losers/043_2026-01-21_loss.png) |
| 44 | 2026-02-08 | Loss | -200.00 | -213.69 | Point-Stop | [044_2026-02-08_loss.png](charts/losers/044_2026-02-08_loss.png) |
| 45 | 2026-02-25 | Loss | -200.00 | -261.69 | Point-Stop | [045_2026-02-25_loss.png](charts/losers/045_2026-02-25_loss.png) |
