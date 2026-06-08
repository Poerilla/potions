# NQ WO 55% gap reversal study

**Master doc (discovery, refinements, cross-market replay):** [`WO_GAP_REVERSAL_STRATEGY.md`](WO_GAP_REVERSAL_STRATEGY.md)

Period: **2023-01-01** → present · Exit: **2ct +50 / runner 300** · SL **50**

## Rules

- **Pre-gap:** ≥1 prior bar fully O+C above WO (short) or below WO (long); wicks may touch WO.
- **Gap candle:** crosses WO with ≥55% of O–C on exit side (cyan dotted = pre-gap context bar).
- **Entry:** limit @ WO from the **next** bar only (not on gap bar).
- **Fill window:** 6 bars after gap; else `no_fill`.
- **Post-gap:** skip if 3-bar swing forms before WO retest, unless gap bar is in that swing.
- **Exit:** 2 contracts — +50 on leg 1, runner ±300, initial SL ∓50, BE on runner after +50.
- Max 2 trades/week; no 2nd trade after TP1 / target win. Charts show **both** long and short setups.
- Orange = long gap · red = short gap · grey diamond = first WO touch · **black outline = HA pin** (causal).
- Yellow dotted = TP1 (+50) · green dotted = runner target · grey solid = WO/BE.

## Charts (121 weeks)

One chart per week with at least one gap setup (filled or not). Paths: `charts/YYYY/YYYY-MM-DD.png`.

Full trade log: [`study_log.csv`](study_log.csv)

| Week | Trades | Setups | Chart |
|---|---|---|---|
| 2023-01-09 | S stop_both -100, L tp1+be +50 | S↓, L↑ | [2023/2023-01-09.png](charts/2023/2023-01-09.png) |
| 2023-01-30 | — | L↑ | [2023/2023-01-30.png](charts/2023/2023-01-30.png) |
| 2023-02-06 | L stop_both -100 | L↑ | [2023/2023-02-06.png](charts/2023/2023-02-06.png) |
| 2023-02-27 | — | L↑ | [2023/2023-02-27.png](charts/2023/2023-02-27.png) |
| 2023-03-06 | S tp1+target +350 | S↓ | [2023/2023-03-06.png](charts/2023/2023-03-06.png) |
| 2023-03-13 | S stop_both -100 | S↓ | [2023/2023-03-13.png](charts/2023/2023-03-13.png) |
| 2023-03-20 | L tp1+target +350 | L↑ | [2023/2023-03-20.png](charts/2023/2023-03-20.png) |
| 2023-03-27 | S tp1+be +50 | S↓ | [2023/2023-03-27.png](charts/2023/2023-03-27.png) |
| 2023-04-03 | S tp1+eod +123 | S↓ | [2023/2023-04-03.png](charts/2023/2023-04-03.png) |
| 2023-04-10 | L tp1+be +50 | S↓, L↑ | [2023/2023-04-10.png](charts/2023/2023-04-10.png) |
| 2023-04-17 | L stop_both -100, S tp1+be +50 | L↑, S↓ | [2023/2023-04-17.png](charts/2023/2023-04-17.png) |
| 2023-04-24 | L stop_both -100 | L↑ | [2023/2023-04-24.png](charts/2023/2023-04-24.png) |
| 2023-05-01 | L stop_both -100 | L↑, S↓ | [2023/2023-05-01.png](charts/2023/2023-05-01.png) |
| 2023-05-08 | S stop_both -100 | S↓, L↑ | [2023/2023-05-08.png](charts/2023/2023-05-08.png) |
| 2023-05-22 | L tp1+be +50 | L↑ | [2023/2023-05-22.png](charts/2023/2023-05-22.png) |
| 2023-05-29 | L tp1+be +50 | L↑ | [2023/2023-05-29.png](charts/2023/2023-05-29.png) |
| 2023-06-05 | L tp1+be +50 | L↑ | [2023/2023-06-05.png](charts/2023/2023-06-05.png) |
| 2023-06-26 | L tp1+be +50 | L↑ | [2023/2023-06-26.png](charts/2023/2023-06-26.png) |
| 2023-07-03 | S tp1+be +50 | S↓ | [2023/2023-07-03.png](charts/2023/2023-07-03.png) |
| 2023-07-17 | — | S↓ | [2023/2023-07-17.png](charts/2023/2023-07-17.png) |
| 2023-07-24 | S tp1+be +50 | L↑, S↓ | [2023/2023-07-24.png](charts/2023/2023-07-24.png) |
| 2023-07-31 | L tp1+be +50 | L↑ | [2023/2023-07-31.png](charts/2023/2023-07-31.png) |
| 2023-08-07 | S tp1+be +50 | S↓ | [2023/2023-08-07.png](charts/2023/2023-08-07.png) |
| 2023-08-21 | — | L↑ | [2023/2023-08-21.png](charts/2023/2023-08-21.png) |
| 2023-09-04 | — | L↑ | [2023/2023-09-04.png](charts/2023/2023-09-04.png) |
| 2023-09-11 | — | S↓ | [2023/2023-09-11.png](charts/2023/2023-09-11.png) |
| 2023-09-18 | S tp1+be +50 | S↓ | [2023/2023-09-18.png](charts/2023/2023-09-18.png) |
| 2023-09-25 | S tp1+be +50 | S↓ | [2023/2023-09-25.png](charts/2023/2023-09-25.png) |
| 2023-10-02 | L stop_both -100 | L↑ | [2023/2023-10-02.png](charts/2023/2023-10-02.png) |
| 2023-10-09 | L stop_both -100, S stop_both -100 | L↑, S↓ | [2023/2023-10-09.png](charts/2023/2023-10-09.png) |
| 2023-10-16 | S tp1+be +50 | S↓ | [2023/2023-10-16.png](charts/2023/2023-10-16.png) |
| 2023-10-23 | — | S↓ | [2023/2023-10-23.png](charts/2023/2023-10-23.png) |
| 2023-10-30 | S stop_both -100 | S↓ | [2023/2023-10-30.png](charts/2023/2023-10-30.png) |
| 2023-11-06 | L tp1+be +50 | L↑ | [2023/2023-11-06.png](charts/2023/2023-11-06.png) |
| 2023-11-13 | S stop_both -100 | S↓ | [2023/2023-11-13.png](charts/2023/2023-11-13.png) |
| 2023-11-20 | — | L↑ | [2023/2023-11-20.png](charts/2023/2023-11-20.png) |
| 2023-12-04 | L tp1+be +50 | L↑ | [2023/2023-12-04.png](charts/2023/2023-12-04.png) |
| 2023-12-18 | S stop_both -100, L tp1+be +50 | S↓, L↑ | [2023/2023-12-18.png](charts/2023/2023-12-18.png) |
| 2024-01-01 | — | S↓ | [2024/2024-01-01.png](charts/2024/2024-01-01.png) |
| 2024-01-08 | S stop_both -100 | S↓ | [2024/2024-01-08.png](charts/2024/2024-01-08.png) |
| 2024-01-22 | L stop_both -100 | L↑ | [2024/2024-01-22.png](charts/2024/2024-01-22.png) |
| 2024-01-29 | S stop_both -100 | S↓, L↑ | [2024/2024-01-29.png](charts/2024/2024-01-29.png) |
| 2024-02-05 | — | S↓, L↑ | [2024/2024-02-05.png](charts/2024/2024-02-05.png) |
| 2024-02-12 | — | L↑ | [2024/2024-02-12.png](charts/2024/2024-02-12.png) |
| 2024-02-26 | L tp1+be +50 | L↑ | [2024/2024-02-26.png](charts/2024/2024-02-26.png) |
| 2024-03-04 | L stop_both -100 | L↑, S↓ | [2024/2024-03-04.png](charts/2024/2024-03-04.png) |
| 2024-03-18 | S tp1+be +50 | S↓ | [2024/2024-03-18.png](charts/2024/2024-03-18.png) |
| 2024-03-25 | L stop_both -100 | L↑ | [2024/2024-03-25.png](charts/2024/2024-03-25.png) |
| 2024-04-01 | S tp1+be +50 | S↓ | [2024/2024-04-01.png](charts/2024/2024-04-01.png) |
| 2024-04-08 | L stop_both -100, S stop_both -100 | L↑, S↓ | [2024/2024-04-08.png](charts/2024/2024-04-08.png) |
| 2024-04-29 | S tp1+be +50 | S↓ | [2024/2024-04-29.png](charts/2024/2024-04-29.png) |
| 2024-05-06 | L tp1+target +350 | L↑ | [2024/2024-05-06.png](charts/2024/2024-05-06.png) |
| 2024-05-20 | L tp1+target +350 | L↑ | [2024/2024-05-20.png](charts/2024/2024-05-20.png) |
| 2024-05-27 | S tp1+target +350 | S↓ | [2024/2024-05-27.png](charts/2024/2024-05-27.png) |
| 2024-06-03 | S tp1+be +50 | S↓ | [2024/2024-06-03.png](charts/2024/2024-06-03.png) |
| 2024-06-10 | — | S↓ | [2024/2024-06-10.png](charts/2024/2024-06-10.png) |
| 2024-06-17 | — | L↑ | [2024/2024-06-17.png](charts/2024/2024-06-17.png) |
| 2024-06-24 | — | S↓, L↑ | [2024/2024-06-24.png](charts/2024/2024-06-24.png) |
| 2024-07-01 | — | S↓, L↑ | [2024/2024-07-01.png](charts/2024/2024-07-01.png) |
| 2024-07-08 | — | L↑ | [2024/2024-07-08.png](charts/2024/2024-07-08.png) |
| 2024-07-15 | S tp1+be +50 | S↓ | [2024/2024-07-15.png](charts/2024/2024-07-15.png) |
| 2024-07-29 | S stop_both -100, L stop_both -100 | S↓, L↑ | [2024/2024-07-29.png](charts/2024/2024-07-29.png) |
| 2024-08-05 | L stop_both -100, S tp1+target +350 | L↑, S↓ | [2024/2024-08-05.png](charts/2024/2024-08-05.png) |
| 2024-08-12 | L stop_both -100, S stop_both -100 | L↑, S↓ | [2024/2024-08-12.png](charts/2024/2024-08-12.png) |
| 2024-08-19 | S tp1+be +50 | S↓ | [2024/2024-08-19.png](charts/2024/2024-08-19.png) |
| 2024-08-26 | S tp1+target +350 | S↓ | [2024/2024-08-26.png](charts/2024/2024-08-26.png) |
| 2024-09-02 | L stop_both -100 | L↑, S↓ | [2024/2024-09-02.png](charts/2024/2024-09-02.png) |
| 2024-09-23 | L stop_both -100 | L↑ | [2024/2024-09-23.png](charts/2024/2024-09-23.png) |
| 2024-09-30 | S stop_both -100 | S↓ | [2024/2024-09-30.png](charts/2024/2024-09-30.png) |
| 2024-10-14 | — | S↓ | [2024/2024-10-14.png](charts/2024/2024-10-14.png) |
| 2024-10-28 | — | S↓ | [2024/2024-10-28.png](charts/2024/2024-10-28.png) |
| 2024-11-04 | — | S↓ | [2024/2024-11-04.png](charts/2024/2024-11-04.png) |
| 2024-11-11 | — | S↓ | [2024/2024-11-11.png](charts/2024/2024-11-11.png) |
| 2024-11-18 | S tp1+be +50 | S↓ | [2024/2024-11-18.png](charts/2024/2024-11-18.png) |
| 2024-11-25 | S stop_both -100 | S↓ | [2024/2024-11-25.png](charts/2024/2024-11-25.png) |
| 2024-12-16 | — | S↓ | [2024/2024-12-16.png](charts/2024/2024-12-16.png) |
| 2024-12-23 | S tp1+be +50 | S↓ | [2024/2024-12-23.png](charts/2024/2024-12-23.png) |
| 2025-01-06 | S tp1+target +350 | S↓ | [2025/2025-01-06.png](charts/2025/2025-01-06.png) |
| 2025-01-13 | L tp1+be +50 | S↓, L↑ | [2025/2025-01-13.png](charts/2025/2025-01-13.png) |
| 2025-01-20 | S eod_both +68 | S↓ | [2025/2025-01-20.png](charts/2025/2025-01-20.png) |
| 2025-01-27 | S tp1+be +50 | S↓ | [2025/2025-01-27.png](charts/2025/2025-01-27.png) |
| 2025-02-17 | S tp1+be +50 | S↓ | [2025/2025-02-17.png](charts/2025/2025-02-17.png) |
| 2025-02-24 | S tp1+target +350 | S↓ | [2025/2025-02-24.png](charts/2025/2025-02-24.png) |
| 2025-03-17 | — | L↑ | [2025/2025-03-17.png](charts/2025/2025-03-17.png) |
| 2025-03-24 | S tp1+be +50 | S↓ | [2025/2025-03-24.png](charts/2025/2025-03-24.png) |
| 2025-03-31 | S tp1+be +50 | S↓ | [2025/2025-03-31.png](charts/2025/2025-03-31.png) |
| 2025-04-07 | S tp1+be +50 | S↓ | [2025/2025-04-07.png](charts/2025/2025-04-07.png) |
| 2025-04-14 | S tp1+be +50 | S↓ | [2025/2025-04-14.png](charts/2025/2025-04-14.png) |
| 2025-04-21 | — | S↓ | [2025/2025-04-21.png](charts/2025/2025-04-21.png) |
| 2025-04-28 | S tp1+be +50 | S↓ | [2025/2025-04-28.png](charts/2025/2025-04-28.png) |
| 2025-05-05 | L tp1+be +50 | L↑ | [2025/2025-05-05.png](charts/2025/2025-05-05.png) |
| 2025-05-19 | S tp1+be +50 | L↑, S↓ | [2025/2025-05-19.png](charts/2025/2025-05-19.png) |
| 2025-06-02 | — | L↑ | [2025/2025-06-02.png](charts/2025/2025-06-02.png) |
| 2025-06-09 | — | S↓ | [2025/2025-06-09.png](charts/2025/2025-06-09.png) |
| 2025-06-30 | S tp1+be +50 | S↓ | [2025/2025-06-30.png](charts/2025/2025-06-30.png) |
| 2025-07-07 | L tp1+be +50 | L↑ | [2025/2025-07-07.png](charts/2025/2025-07-07.png) |
| 2025-07-14 | S tp1+be +50 | S↓ | [2025/2025-07-14.png](charts/2025/2025-07-14.png) |
| 2025-07-21 | — | S↓ | [2025/2025-07-21.png](charts/2025/2025-07-21.png) |
| 2025-07-28 | — | S↓ | [2025/2025-07-28.png](charts/2025/2025-07-28.png) |
| 2025-08-25 | L stop_both -100 | S↓, L↑ | [2025/2025-08-25.png](charts/2025/2025-08-25.png) |
| 2025-09-01 | L tp1+be +50 | S↓, L↑ | [2025/2025-09-01.png](charts/2025/2025-09-01.png) |
| 2025-09-08 | L tp1+be +50 | L↑ | [2025/2025-09-08.png](charts/2025/2025-09-08.png) |
| 2025-09-22 | L tp1+be +50 | S↓, L↑ | [2025/2025-09-22.png](charts/2025/2025-09-22.png) |
| 2025-09-29 | S tp1+be +50 | S↓ | [2025/2025-09-29.png](charts/2025/2025-09-29.png) |
| 2025-10-06 | S stop_both -100 | S↓, L↑ | [2025/2025-10-06.png](charts/2025/2025-10-06.png) |
| 2025-10-13 | — | S↓ | [2025/2025-10-13.png](charts/2025/2025-10-13.png) |
| 2025-10-20 | S tp1+be +50 | S↓ | [2025/2025-10-20.png](charts/2025/2025-10-20.png) |
| 2025-11-03 | S tp1+be +50 | S↓ | [2025/2025-11-03.png](charts/2025/2025-11-03.png) |
| 2025-11-10 | S tp1+target +350 | S↓ | [2025/2025-11-10.png](charts/2025/2025-11-10.png) |
| 2025-11-17 | L stop_both -100 | L↑, S↓ | [2025/2025-11-17.png](charts/2025/2025-11-17.png) |
| 2025-12-01 | L tp1+be +50 | L↑ | [2025/2025-12-01.png](charts/2025/2025-12-01.png) |
| 2025-12-08 | S stop_both -100 | S↓ | [2025/2025-12-08.png](charts/2025/2025-12-08.png) |
| 2025-12-15 | L tp1+be +50 | L↑ | [2025/2025-12-15.png](charts/2025/2025-12-15.png) |
| 2025-12-22 | L tp1+be +50 | L↑ | [2025/2025-12-22.png](charts/2025/2025-12-22.png) |
| 2026-01-12 | L tp1+be +50 | L↑ | [2026/2026-01-12.png](charts/2026/2026-01-12.png) |
| 2026-01-19 | L stop_both -100 | L↑ | [2026/2026-01-19.png](charts/2026/2026-01-19.png) |
| 2026-02-02 | S tp1+target +350 | L↑, S↓ | [2026/2026-02-02.png](charts/2026/2026-02-02.png) |
| 2026-02-09 | S stop_both -100, L tp1+be +50 | S↓, L↑ | [2026/2026-02-09.png](charts/2026/2026-02-09.png) |
| 2026-02-16 | — | S↓, L↑ | [2026/2026-02-16.png](charts/2026/2026-02-16.png) |
| 2026-02-23 | — | L↑, S↓ | [2026/2026-02-23.png](charts/2026/2026-02-23.png) |
| 2026-03-02 | S tp1+be +50 | S↓ | [2026/2026-03-02.png](charts/2026/2026-03-02.png) |

### Both sides (2ct +50/300)

- Trades: **100** · Net: **+3140.5 pts** · Win rate: **65.0%**
- Targets: 11 · Stops: 35 · EOD/other: 54
- Profit factor: **1.90** · Avg/trade: **+31.41 pts**

| Year | Trades | Net pts |
|---|---:|---:|
| 2023 | 34 | +423.0 |
| 2024 | 30 | +600.0 |
| 2025 | 30 | +1817.5 |
| 2026 | 6 | +300.0 |

### Short only (2ct +50/300)

- Trades: **62** · Net: **+3040.5 pts** · Win rate: **69.4%**
- Targets: 9 · Stops: 19 · EOD/other: 34
- Profit factor: **2.60** · Avg/trade: **+49.04 pts**

| Year | Trades | Net pts |
|---|---:|---:|
| 2023 | 18 | +223.0 |
| 2024 | 20 | +550.0 |
| 2025 | 21 | +1967.5 |
| 2026 | 3 | +300.0 |


Short-only log: [`short_only_trades_2023plus.csv`](short_only_trades_2023plus.csv)

## Side split (both sides)

- **long:** 43 trades, net **+350.0 pts**
- **short:** 57 trades, net **+2790.5 pts**
