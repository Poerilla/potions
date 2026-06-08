# v2e causal live charts (15m breaker close-confirm)

Strict next-bar causal simulation. Charts are split into `winners/` and `losers/`.

| Date | Side | Breaker | Close Confirm | Causal Net | Causal Result | Legacy Net | Legacy Result | Chart |
|---|:---:|:---:|:---:|---:|---|---:|---|---|
| 2021-03-08 | short | 15m | yes | +364.50 | Win | +287.00 | Win | [winners/win_01_2021-03-08_Short.png](winners/win_01_2021-03-08_Short.png) |
| 2021-03-25 | long | 15m | yes | -121.00 | Loss | +149.00 | Win | [losers/loss_01_2021-03-25_Long.png](losers/loss_01_2021-03-25_Long.png) |
| 2021-04-12 | long | 15m | yes | +11.00 | EOD-Win | +11.00 | EOD-Win | [winners/win_02_2021-04-12_Long.png](winners/win_02_2021-04-12_Long.png) |
| 2021-04-28 | long | 15m | yes | -103.00 | Loss | -116.50 | Loss | [losers/loss_02_2021-04-28_Long.png](losers/loss_02_2021-04-28_Long.png) |
| 2021-05-06 | long | 15m | yes | +215.50 | EOD-Win | +221.00 | Win | [winners/win_03_2021-05-06_Long.png](winners/win_03_2021-05-06_Long.png) |
| 2021-05-26 | long | 15m | yes | -15.50 | EOD-Loss | +33.50 | EOD-Win | [losers/loss_03_2021-05-26_Long.png](losers/loss_03_2021-05-26_Long.png) |
| 2021-06-03 | long | 15m | yes | -47.00 | EOD-Loss | -87.00 | EOD-Loss | [losers/loss_04_2021-06-03_Long.png](losers/loss_04_2021-06-03_Long.png) |
| 2021-06-09 | short | 15m | yes | +50.50 | EOD-Win | +53.50 | EOD-Win | [winners/win_04_2021-06-09_Short.png](winners/win_04_2021-06-09_Short.png) |
| 2021-07-06 | long | 15m | yes | +59.50 | EOD-Win |  |  | [winners/win_05_2021-07-06_Long.png](winners/win_05_2021-07-06_Long.png) |
| 2021-07-28 | short | 15m | yes | -44.50 | Loss | -44.00 | Loss | [losers/loss_05_2021-07-28_Short.png](losers/loss_05_2021-07-28_Short.png) |
| 2021-08-04 | long | 15m | yes | -3.00 | EOD-Loss | +27.00 | EOD-Win | [losers/loss_06_2021-08-04_Long.png](losers/loss_06_2021-08-04_Long.png) |
| 2021-08-26 | short | 15m | yes | +82.50 | EOD-Win | +113.00 | EOD-Win | [winners/win_06_2021-08-26_Short.png](winners/win_06_2021-08-26_Short.png) |
| 2021-09-09 | short | 15m | yes | +93.50 | Win | +83.00 | Win | [winners/win_07_2021-09-09_Short.png](winners/win_07_2021-09-09_Short.png) |
| 2021-09-14 | long | 15m | yes | -127.00 | Loss | +86.00 | Win | [losers/loss_07_2021-09-14_Long.png](losers/loss_07_2021-09-14_Long.png) |
| 2021-10-25 | short | 15m | yes | -119.50 | Loss | -97.00 | Loss | [losers/loss_08_2021-10-25_Short.png](losers/loss_08_2021-10-25_Short.png) |
| 2021-11-01 | long | 15m | yes | +133.00 | EOD-Win | +121.00 | EOD-Win | [winners/win_08_2021-11-01_Long.png](winners/win_08_2021-11-01_Long.png) |
| 2021-11-18 | short | 15m | yes | -138.00 | Loss | -96.50 | Loss | [losers/loss_09_2021-11-18_Short.png](losers/loss_09_2021-11-18_Short.png) |
| 2021-12-09 | short | 15m | yes | +273.50 | Win | +208.00 | Win | [winners/win_09_2021-12-09_Short.png](winners/win_09_2021-12-09_Short.png) |
| 2021-12-14 | long | 15m | yes | -138.00 | Loss | -109.00 | Loss | [losers/loss_10_2021-12-14_Long.png](losers/loss_10_2021-12-14_Long.png) |
| 2022-01-19 | short | 15m | yes | +262.00 | Win | +136.00 | Win | [winners/win_10_2022-01-19_Short.png](winners/win_10_2022-01-19_Short.png) |
| 2022-01-25 | long | 15m | yes | -54.50 | EOD-Loss | +335.00 | Win | [losers/loss_11_2022-01-25_Long.png](losers/loss_11_2022-01-25_Long.png) |
| 2022-02-07 | short | 15m | yes | +301.00 | Win | +271.50 | Win | [winners/win_11_2022-02-07_Short.png](winners/win_11_2022-02-07_Short.png) |
| 2022-02-14 | short | 15m | yes | -98.00 | EOD-Loss | -245.00 | Loss | [losers/loss_12_2022-02-14_Short.png](losers/loss_12_2022-02-14_Short.png) |
| 2022-03-14 | long | 15m | yes | -237.50 | Loss | -176.00 | Loss | [losers/loss_13_2022-03-14_Long.png](losers/loss_13_2022-03-14_Long.png) |
| 2022-03-16 | short | 15m | yes | +444.00 | Win | +155.50 | Win | [winners/win_12_2022-03-16_Short.png](winners/win_12_2022-03-16_Short.png) |
| 2022-04-21 | short | 15m | yes | +278.50 | Win | +278.50 | Win | [winners/win_13_2022-04-21_Short.png](winners/win_13_2022-04-21_Short.png) |
| 2022-04-29 | long | 15m | yes | -219.50 | Loss | -298.00 | Loss | [losers/loss_14_2022-04-29_Long.png](losers/loss_14_2022-04-29_Long.png) |
| 2022-05-12 | short | 15m | yes | -67.50 | EOD-Loss | +221.50 | Win | [losers/loss_15_2022-05-12_Short.png](losers/loss_15_2022-05-12_Short.png) |
| 2022-05-30 | long | 15m | yes | +49.00 | EOD-Win | +82.00 | Win | [winners/win_14_2022-05-30_Long.png](winners/win_14_2022-05-30_Long.png) |
| 2022-06-02 | long | 15m | yes | +409.50 | Win | +267.50 | Win | [winners/win_15_2022-06-02_Long.png](winners/win_15_2022-06-02_Long.png) |
| 2022-06-09 | long | 15m | yes | -236.50 | Loss | -186.00 | Loss | [losers/loss_16_2022-06-09_Long.png](losers/loss_16_2022-06-09_Long.png) |
| 2022-07-12 | short | 15m | yes | +270.50 | Win | +269.50 | Win | [winners/win_16_2022-07-12_Short.png](winners/win_16_2022-07-12_Short.png) |
| 2022-07-18 | long | 15m | yes | -79.50 | Loss | -137.50 | Loss | [losers/loss_17_2022-07-18_Long.png](losers/loss_17_2022-07-18_Long.png) |
| 2022-08-01 | long | 15m | yes | -53.00 | EOD-Loss | +161.50 | Win | [losers/loss_18_2022-08-01_Long.png](losers/loss_18_2022-08-01_Long.png) |
| 2022-08-17 | long | 15m | yes | +30.50 | EOD-Win | +203.00 | Win | [winners/win_17_2022-08-17_Long.png](winners/win_17_2022-08-17_Long.png) |
| 2022-09-26 | short | 15m | yes | +43.50 | EOD-Win | +233.50 | Win | [winners/win_18_2022-09-26_Short.png](winners/win_18_2022-09-26_Short.png) |
| 2022-09-30 | long | 15m | yes | -247.00 | Loss | -206.50 | Loss | [losers/loss_19_2022-09-30_Long.png](losers/loss_19_2022-09-30_Long.png) |
| 2022-10-11 | long | 15m | yes | -407.50 | Loss | +233.00 | Win | [losers/loss_20_2022-10-11_Long.png](losers/loss_20_2022-10-11_Long.png) |
| 2022-10-24 | long | 15m | yes | +103.50 | EOD-Win | +167.00 | EOD-Win | [winners/win_19_2022-10-24_Long.png](winners/win_19_2022-10-24_Long.png) |
| 2022-11-03 | long | 15m | yes | -247.00 | EOD-Loss | -107.00 | EOD-Loss | [losers/loss_21_2022-11-03_Long.png](losers/loss_21_2022-11-03_Long.png) |
| 2022-11-11 | long | 15m | yes | +250.00 | EOD-Win | +321.00 | Win | [winners/win_20_2022-11-11_Long.png](winners/win_20_2022-11-11_Long.png) |
| 2022-12-08 | long | 15m | yes | +126.00 | EOD-Win |  |  | [winners/win_21_2022-12-08_Long.png](winners/win_21_2022-12-08_Long.png) |
| 2022-12-28 | long | 15m | yes | -180.50 | Loss |  |  | [losers/loss_22_2022-12-28_Long.png](losers/loss_22_2022-12-28_Long.png) |
| 2023-01-19 | long | 15m | yes | -45.50 | EOD-Loss |  |  | [losers/loss_23_2023-01-19_Long.png](losers/loss_23_2023-01-19_Long.png) |
| 2023-01-25 | long | 15m | yes | +289.00 | Win | -131.00 | Loss | [winners/win_22_2023-01-25_Long.png](winners/win_22_2023-01-25_Long.png) |
| 2023-02-07 | short | 15m | yes | -486.00 | Loss | -105.00 | Loss | [losers/loss_24_2023-02-07_Short.png](losers/loss_24_2023-02-07_Short.png) |
| 2023-02-09 | short | 15m | yes | +226.50 | Win | +135.50 | Win | [winners/win_23_2023-02-09_Short.png](winners/win_23_2023-02-09_Short.png) |
| 2023-03-17 | short | 15m | yes | +85.50 | EOD-Win | +251.50 | Win | [winners/win_24_2023-03-17_Short.png](winners/win_24_2023-03-17_Short.png) |
| 2023-03-30 | short | 15m | yes | -40.00 | EOD-Loss | -121.00 | Loss | [losers/loss_25_2023-03-30_Short.png](losers/loss_25_2023-03-30_Short.png) |
| 2023-04-10 | long | 15m | yes | +104.50 | EOD-Win | +63.50 | Win | [winners/win_25_2023-04-10_Long.png](winners/win_25_2023-04-10_Long.png) |
