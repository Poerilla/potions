# NQ v2b 1/1/3 Stats

Broker-like `Engine + PaperBroker + StrategyPlugin` replay with 1-tick slippage, stop gap-through, stop-first same-bar ordering, and `$1.50` per closed unit. Sizing is `entry_qty=5`, `tp1_qty=1`, `tp2_qty=1`, runner `3`.

## Summary

| Metric | Value |
|---|---:|
| Regime sessions | 1164 |
| Campaigns | 1386 |
| Units | 6900 |
| Net | $867,355.00 |
| Return on $75,000 reference | 1156.5% |
| Closed DD | $-116,718.50 |
| Max MTM / intrabar stress DD | $-118,093.50 |
| Campaign win rate | 53.82% |
| Unit win rate | 38.55% |
| Campaign PF | 1.189 |
| Unit PF | 1.187 |
| Net / stress DD | 7.34 |
| Max open units | 5 |
| Avg campaign | $625.80 |
| Median campaign | $742.50 |
| Best campaign | $64,947.50 |
| Worst campaign | $-28,482.50 |
| Max campaign losing streak | 6 |
| Max campaign winning streak | 16 |

## Yearly Breakdown

|   Year |   Trades |   Units | Net         | Return on ref   | Closed DD    | MTM Stress DD   | Win %   |   PF | Avg Campaign   | Best Campaign   | Worst Campaign   |
|-------:|---------:|--------:|:------------|:----------------|:-------------|:----------------|:--------|-----:|:---------------|:----------------|:-----------------|
|   2021 |      300 |    1493 | $209,235.50 | 279.0%          | $-74,367.00  | $-74,492.00     | 54.7%   | 1.25 | $697.45        | $28,712.50      | $-19,107.50      |
|   2022 |       57 |     285 | $48,922.50  | 65.2%           | $-78,021.00  | $-79,071.00     | 54.4%   | 1.17 | $858.29        | $28,832.50      | $-21,032.50      |
|   2023 |      311 |    1552 | $56,962.00  | 75.9%           | $-90,229.50  | $-91,329.50     | 51.8%   | 1.07 | $183.16        | $28,757.50      | $-13,382.50      |
|   2024 |      382 |    1900 | $193,425.00 | 257.9%          | $-116,718.50 | $-118,093.50    | 52.9%   | 1.16 | $506.35        | $48,317.50      | $-20,382.50      |
|   2025 |      277 |    1378 | $207,028.00 | 276.0%          | $-105,985.00 | $-106,485.00    | 54.5%   | 1.18 | $747.39        | $64,947.50      | $-24,982.50      |
|   2026 |       59 |     292 | $151,782.00 | 202.4%          | $-82,030.00  | $-82,655.00     | 62.7%   | 1.63 | $2,572.58      | $37,667.50      | $-28,482.50      |

## Exit Reasons

| Exit        |   Units | Net            | Avg Unit   |
|:------------|--------:|:---------------|:-----------|
| eod_close   |    2202 | $3,475,467.00  | $1,578.32  |
| runner_stop |    1094 | $-50,676.00    | $-46.32    |
| tp1         |     656 | $984,526.00    | $1,500.80  |
| tp2         |     263 | $720,015.50    | $2,737.70  |
| wide_stop   |    2685 | $-4,261,977.50 | $-1,587.33 |

## Direction Split

| Direction   |   Units | Net         | Avg Unit   |
|:------------|--------:|:------------|:-----------|
| Long        |    3522 | $400,032.00 | $113.58    |
| Short       |    3378 | $467,323.00 | $138.34    |

## Read

- This is the best plain NQ v2b OCO sizing from the sweep by Net/Stress.
- It is much stronger than NQ TP1-only, but the stress budget is six figures, so this belongs in a larger-account paper/live track.
- The prior-opposed ST+PMC gate is a separate research upgrade; this document is the plain all-days v2b OCO variant.

## Files

- `summary.csv` / `SUMMARY_partial.md`
- `nq_1_1_3_yearly.csv`
- `nq_1_1_3_exit_reason.csv`
- `nq_1_1_3_direction.csv`
- `states/nq_v2b_sizing_S_1_1_3/`