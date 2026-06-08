# MNQ Lingering Bullish ATR Stop Short Study

Short-only first pass.

Rules:
- Daily ATR Supertrend-style stop: ATR(14) x 3.
- On bullish-to-bearish ATR flip, extend the prior bullish ATR stop for 3 week(s).
- While the ATR trend remains bearish, wait for the first red daily candle that closes below that lingering line.
- After that signal close, place a sell limit at the lingering line on subsequent daily bars.
- Entry size: 1 contract. Target: 100 points. Intraday point stop: 100 points.
- Also exit at the next daily open after a daily close back above the lingering line.
- If stop and target are both inside the same daily bar, the model uses stop-first ordering.
- Fill-bar ordering is conservative: if the day opens below the sell limit and only later rallies into the limit, same-day target touches are ignored because the low may have printed before the fill.

Causality note: no same-day signal fill is allowed. The sell limit becomes live on the session after the signal candle closes.

## Results

Lingering lines found: 31  ·  Filled trades: 29  ·  Wins: 7  ·  Losses: 22  ·  Win rate: 24.1%  ·  Profit factor: 0.45
Net: -848.46 pts ($-1,697)
Closed-trade max DD: -952.15 pts ($-1,904)
Worst MAE: -509.48 pts ($-1,019)  ·  Avg MAE: -112.30 pts ($-225)

## Audit Status

| Status | Count |
|---|---:|
| filled | 29 |
| limit_not_filled | 2 |

## Exit Reasons

| Exit Reason | Count |
|---|---:|
| Close-Over-Line-Next-Open | 10 |
| Point-Stop | 12 |
| Target | 7 |

## Charts

| Trade | Fill Date | Result | Net Pts | MAE Pts | Exit | Chart |
|---:|---|---|---:|---:|---|---|
| 1 | 2019-05-16 | Loss | -30.88 | -63.62 | Close-Over-Line-Next-Open | [001_2019-05-16_loss.png](charts/losers/001_2019-05-16_loss.png) |
| 2 | 2019-08-13 | Win | +100.00 | -18.58 | Target | [002_2019-08-13_win.png](charts/winners/002_2019-08-13_win.png) |
| 3 | 2019-10-03 | Loss | -65.43 | -81.18 | Close-Over-Line-Next-Open | [003_2019-10-03_loss.png](charts/losers/003_2019-10-03_loss.png) |
| 4 | 2020-09-04 | Win | +100.00 | -88.55 | Target | [004_2020-09-04_win.png](charts/winners/004_2020-09-04_win.png) |
| 5 | 2020-10-29 | Loss | -100.00 | -106.40 | Point-Stop | [005_2020-10-29_loss.png](charts/losers/005_2020-10-29_loss.png) |
| 6 | 2021-02-01 | Loss | -100.00 | -329.45 | Point-Stop | [006_2021-02-01_loss.png](charts/losers/006_2021-02-01_loss.png) |
| 7 | 2021-02-23 | Win | +100.00 | -35.81 | Target | [007_2021-02-23_win.png](charts/winners/007_2021-02-23_win.png) |
| 8 | 2021-05-14 | Win | +100.00 | -29.57 | Target | [008_2021-05-14_win.png](charts/winners/008_2021-05-14_win.png) |
| 9 | 2021-09-19 | Loss | -38.44 | -41.44 | Close-Over-Line-Next-Open | [009_2021-09-19_loss.png](charts/losers/009_2021-09-19_loss.png) |
| 10 | 2021-11-28 | Loss | -60.05 | -68.80 | Close-Over-Line-Next-Open | [010_2021-11-28_loss.png](charts/losers/010_2021-11-28_loss.png) |
| 11 | 2022-01-11 | Loss | -100.00 | -122.95 | Point-Stop | [011_2022-01-11_loss.png](charts/losers/011_2022-01-11_loss.png) |
| 12 | 2022-04-12 | Loss | -100.00 | -187.73 | Point-Stop | [012_2022-04-12_loss.png](charts/losers/012_2022-04-12_loss.png) |
| 13 | 2022-06-15 | Loss | -23.64 | -92.64 | Close-Over-Line-Next-Open | [013_2022-06-15_loss.png](charts/losers/013_2022-06-15_loss.png) |
| 14 | 2022-09-12 | Loss | -2.48 | -22.23 | Close-Over-Line-Next-Open | [014_2022-09-12_loss.png](charts/losers/014_2022-09-12_loss.png) |
| 15 | 2022-12-21 | Loss | -100.00 | -104.32 | Point-Stop | [015_2022-12-21_loss.png](charts/losers/015_2022-12-21_loss.png) |
| 16 | 2023-03-12 | Loss | -100.00 | -221.82 | Point-Stop | [016_2023-03-12_loss.png](charts/losers/016_2023-03-12_loss.png) |
| 17 | 2023-08-06 | Loss | -20.69 | -21.94 | Close-Over-Line-Next-Open | [017_2023-08-06_loss.png](charts/losers/017_2023-08-06_loss.png) |
| 18 | 2023-09-22 | Win | +100.00 | -14.65 | Target | [018_2023-09-22_win.png](charts/winners/018_2023-09-22_win.png) |
| 19 | 2023-11-01 | Loss | -100.00 | -167.28 | Point-Stop | [019_2023-11-01_loss.png](charts/losers/019_2023-11-01_loss.png) |
| 20 | 2024-01-08 | Loss | -100.00 | -170.22 | Point-Stop | [020_2024-01-08_loss.png](charts/losers/020_2024-01-08_loss.png) |
| 21 | 2024-04-16 | Win | +100.00 | -34.10 | Target | [021_2024-04-16_win.png](charts/winners/021_2024-04-16_win.png) |
| 22 | 2024-09-10 | Loss | -53.66 | -92.91 | Close-Over-Line-Next-Open | [022_2024-09-10_loss.png](charts/losers/022_2024-09-10_loss.png) |
| 23 | 2024-12-19 | Loss | -100.00 | -103.32 | Point-Stop | [023_2024-12-19_loss.png](charts/losers/023_2024-12-19_loss.png) |
| 24 | 2025-02-26 | Win | +100.00 | -77.92 | Target | [024_2025-02-26_win.png](charts/winners/024_2025-02-26_win.png) |
| 25 | 2025-08-03 | Loss | -11.25 | -15.75 | Close-Over-Line-Next-Open | [025_2025-08-03_loss.png](charts/losers/025_2025-08-03_loss.png) |
| 26 | 2025-10-12 | Loss | -100.00 | -248.17 | Point-Stop | [026_2025-10-12_loss.png](charts/losers/026_2025-10-12_loss.png) |
| 27 | 2025-11-14 | Loss | -100.00 | -124.23 | Point-Stop | [027_2025-11-14_loss.png](charts/losers/027_2025-11-14_loss.png) |
| 28 | 2026-01-21 | Loss | -100.00 | -509.48 | Point-Stop | [028_2026-01-21_loss.png](charts/losers/028_2026-01-21_loss.png) |
| 29 | 2026-02-08 | Loss | -41.94 | -61.69 | Close-Over-Line-Next-Open | [029_2026-02-08_loss.png](charts/losers/029_2026-02-08_loss.png) |
