# v2e causal live charts (5m breaker re-entry)

Strict next-bar causal simulation. Charts are split into `winners/` and `losers/`.

| Date | Side | Attempt | Breaker | Close Confirm | Causal Net | Causal Result | Legacy Net | Legacy Result | Chart |
|---|:---:|---:|:---:|:---:|---:|---|---:|---|---|
| 2021-03-12 | long | 1 | 5m | no | -119.00 | Loss | -119.00 | Loss | [losers/loss_01_2021-03-12_Long.png](losers/loss_01_2021-03-12_Long.png) |
| 2021-03-17 | long | 1 | 5m | no | +230.50 | Win | +230.50 | Win | [winners/win_01_2021-03-17_Long.png](winners/win_01_2021-03-17_Long.png) |
| 2021-04-07 | long | 1 | 5m | no | +138.50 | Win | +138.50 | Win | [winners/win_02_2021-04-07_Long.png](winners/win_02_2021-04-07_Long.png) |
| 2021-04-08 | short | 1 | 5m | no | -72.50 | Loss | -72.50 | Loss | [losers/loss_02_2021-04-08_Short.png](losers/loss_02_2021-04-08_Short.png) |
| 2021-05-06 | short | 1 | 5m | no | -60.00 | Loss | +63.00 | Win | [losers/loss_03_2021-05-06_Short.png](losers/loss_03_2021-05-06_Short.png) |
| 2021-05-13 | short | 2 | 5m | no | +109.00 | EOD-Win | -162.50 | Loss | [winners/win_03_2021-05-13_Short.png](winners/win_03_2021-05-13_Short.png) |
| 2021-06-09 | short | 2 | 5m | no | +83.00 | EOD-Win | +53.50 | EOD-Win | [winners/win_04_2021-06-09_Short.png](winners/win_04_2021-06-09_Short.png) |
| 2021-06-18 | long | 2 | 5m | no | -40.50 | EOD-Loss | -155.50 | Loss | [losers/loss_04_2021-06-18_Long.png](losers/loss_04_2021-06-18_Long.png) |
| 2021-07-14 | short | 2 | 5m | no | +98.50 | Win | -67.50 | Loss | [winners/win_05_2021-07-14_Short.png](winners/win_05_2021-07-14_Short.png) |
| 2021-07-21 | short | 1 | 5m | no | -85.00 | Loss | -85.00 | Loss | [losers/loss_05_2021-07-21_Short.png](losers/loss_05_2021-07-21_Short.png) |
| 2021-08-25 | short | 1 | 5m | no | -5.00 | EOD-Loss | -5.00 | EOD-Loss | [losers/loss_06_2021-08-25_Short.png](losers/loss_06_2021-08-25_Short.png) |
| 2021-08-26 | short | 1 | 5m | no | +113.00 | EOD-Win | +113.00 | EOD-Win | [winners/win_06_2021-08-26_Short.png](winners/win_06_2021-08-26_Short.png) |
| 2021-09-14 | long | 1 | 5m | no | +86.00 | Win | +86.00 | Win | [winners/win_07_2021-09-14_Long.png](winners/win_07_2021-09-14_Long.png) |
| 2021-09-29 | long | 1 | 5m | no | -94.50 | Loss | -131.50 | Loss | [losers/loss_07_2021-09-29_Long.png](losers/loss_07_2021-09-29_Long.png) |
| 2021-10-15 | short | 2 | 5m | no | -32.50 | Loss | +47.00 | Win | [losers/loss_08_2021-10-15_Short.png](losers/loss_08_2021-10-15_Short.png) |
| 2021-10-15 | short | 1 | 5m | no | +47.00 | Win | +47.00 | Win | [winners/win_08_2021-10-15_Short.png](winners/win_08_2021-10-15_Short.png) |
| 2021-11-17 | long | 1 | 5m | no | +123.00 | Win | +123.00 | Win | [winners/win_09_2021-11-17_Long.png](winners/win_09_2021-11-17_Long.png) |
| 2021-11-18 | short | 1 | 5m | no | -96.50 | Loss | -96.50 | Loss | [losers/loss_09_2021-11-18_Short.png](losers/loss_09_2021-11-18_Short.png) |
| 2021-12-09 | short | 1 | 5m | no | +208.00 | Win | +208.00 | Win | [winners/win_10_2021-12-09_Short.png](winners/win_10_2021-12-09_Short.png) |
| 2021-12-14 | long | 1 | 5m | no | -109.00 | Loss | -109.00 | Loss | [losers/loss_10_2021-12-14_Long.png](losers/loss_10_2021-12-14_Long.png) |
| 2022-01-12 | short | 2 | 5m | no | +209.50 | Win | -133.50 | Loss | [winners/win_11_2022-01-12_Short.png](winners/win_11_2022-01-12_Short.png) |
| 2022-01-21 | short | 1 | 5m | no | -277.00 | Loss | -277.00 | Loss | [losers/loss_11_2022-01-21_Short.png](losers/loss_11_2022-01-21_Short.png) |
| 2022-02-08 | long | 1 | 5m | no | +302.50 | Win | +302.50 | Win | [winners/win_12_2022-02-08_Long.png](winners/win_12_2022-02-08_Long.png) |
| 2022-02-18 | long | 1 | 5m | no | -262.00 | Loss | -262.00 | Loss | [losers/loss_12_2022-02-18_Long.png](losers/loss_12_2022-02-18_Long.png) |
| 2022-03-10 | long | 1 | 5m | no | -185.00 | Loss | -185.00 | Loss | [losers/loss_13_2022-03-10_Long.png](losers/loss_13_2022-03-10_Long.png) |
| 2022-03-23 | short | 1 | 5m | no | +258.50 | Win | +258.50 | Win | [winners/win_13_2022-03-23_Short.png](winners/win_13_2022-03-23_Short.png) |
| 2022-04-07 | short | 1 | 5m | no | -293.50 | Loss | -293.50 | Loss | [losers/loss_14_2022-04-07_Short.png](losers/loss_14_2022-04-07_Short.png) |
| 2022-04-21 | short | 1 | 5m | no | +278.50 | Win | +278.50 | Win | [winners/win_14_2022-04-21_Short.png](winners/win_14_2022-04-21_Short.png) |
| 2022-05-10 | short | 1 | 5m | no | +129.50 | EOD-Win | +129.50 | EOD-Win | [winners/win_15_2022-05-10_Short.png](winners/win_15_2022-05-10_Short.png) |
| 2022-05-19 | short | 1 | 5m | no | -282.50 | Loss | -282.50 | Loss | [losers/loss_15_2022-05-19_Short.png](losers/loss_15_2022-05-19_Short.png) |
| 2022-06-06 | short | 1 | 5m | no | -117.00 | Loss | -187.00 | Loss | [losers/loss_16_2022-06-06_Short.png](losers/loss_16_2022-06-06_Short.png) |
| 2022-06-06 | short | 2 | 5m | no | +144.50 | EOD-Win | -187.00 | Loss | [winners/win_16_2022-06-06_Short.png](winners/win_16_2022-06-06_Short.png) |
| 2022-07-01 | short | 2 | 5m | no | -403.00 | Loss | -403.00 | Loss | [losers/loss_17_2022-07-01_Short.png](losers/loss_17_2022-07-01_Short.png) |
| 2022-07-05 | long | 1 | 5m | no | +223.50 | Win | +223.50 | Win | [winners/win_17_2022-07-05_Long.png](winners/win_17_2022-07-05_Long.png) |
| 2022-08-11 | long | 1 | 5m | no | -114.00 | Loss | -114.00 | Loss | [losers/loss_18_2022-08-11_Long.png](losers/loss_18_2022-08-11_Long.png) |
| 2022-08-18 | short | 1 | 5m | no | +32.00 | EOD-Win | +68.00 | Win | [winners/win_18_2022-08-18_Short.png](winners/win_18_2022-08-18_Short.png) |
| 2022-09-21 | long | 1 | 5m | no | -609.00 | Loss | -609.00 | Loss | [losers/loss_19_2022-09-21_Long.png](losers/loss_19_2022-09-21_Long.png) |
| 2022-09-30 | short | 1 | 5m | no | +205.50 | Win | +205.50 | Win | [winners/win_19_2022-09-30_Short.png](winners/win_19_2022-09-30_Short.png) |
| 2022-10-12 | long | 1 | 5m | no | -77.00 | EOD-Loss | -77.00 | EOD-Loss | [losers/loss_20_2022-10-12_Long.png](losers/loss_20_2022-10-12_Long.png) |
| 2022-10-19 | long | 1 | 5m | no | +52.50 | EOD-Win | +52.50 | EOD-Win | [winners/win_20_2022-10-19_Long.png](winners/win_20_2022-10-19_Long.png) |
| 2022-11-01 | short | 1 | 5m | no | +132.50 | Win | +132.50 | Win | [winners/win_21_2022-11-01_Short.png](winners/win_21_2022-11-01_Short.png) |
| 2022-11-18 | long | 1 | 5m | no | -140.00 | Loss | -140.00 | Loss | [losers/loss_21_2022-11-18_Long.png](losers/loss_21_2022-11-18_Long.png) |
| 2022-12-12 | long | 1 | 5m | no | -112.00 | Loss | -112.00 | Loss | [losers/loss_22_2022-12-12_Long.png](losers/loss_22_2022-12-12_Long.png) |
| 2022-12-28 | short | 1 | 5m | no | +180.00 | EOD-Win | +180.00 | EOD-Win | [winners/win_22_2022-12-28_Short.png](winners/win_22_2022-12-28_Short.png) |
| 2023-01-03 | short | 1 | 5m | no | +276.00 | Win | +276.00 | Win | [winners/win_23_2023-01-03_Short.png](winners/win_23_2023-01-03_Short.png) |
| 2023-01-10 | short | 1 | 5m | no | -200.00 | Loss | -200.00 | Loss | [losers/loss_23_2023-01-10_Short.png](losers/loss_23_2023-01-10_Short.png) |
| 2023-02-07 | short | 2 | 5m | no | -486.00 | Loss | -105.00 | Loss | [losers/loss_24_2023-02-07_Short.png](losers/loss_24_2023-02-07_Short.png) |
| 2023-02-27 | short | 1 | 5m | no | +44.00 | EOD-Win | +44.00 | EOD-Win | [winners/win_24_2023-02-27_Short.png](winners/win_24_2023-02-27_Short.png) |
| 2023-03-08 | short | 1 | 5m | no | -99.50 | Loss | -99.50 | Loss | [losers/loss_25_2023-03-08_Short.png](losers/loss_25_2023-03-08_Short.png) |
| 2023-03-17 | short | 1 | 5m | no | +251.50 | Win | +251.50 | Win | [winners/win_25_2023-03-17_Short.png](winners/win_25_2023-03-17_Short.png) |
