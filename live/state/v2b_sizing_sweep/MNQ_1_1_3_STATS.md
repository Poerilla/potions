# MNQ v2b 1/1/3 Stats

Broker-like `Engine + PaperBroker + StrategyPlugin` replay with 1-tick slippage, stop gap-through, stop-first same-bar ordering, and `$1.50` per closed unit. Sizing is `entry_qty=5`, `tp1_qty=1`, `tp2_qty=1`, runner `3`.

## Summary

| Metric | Value |
|---|---:|
| Regime sessions | 1164 |
| Campaigns | 1384 |
| Units | 6886 |
| Net | $74,441.50 |
| Return on $7,500 reference | 992.6% |
| Closed DD | $-12,234.50 |
| Max MTM / intrabar stress DD | $-12,372.00 |
| Campaign win rate | 53.61% |
| Unit win rate | 38.32% |
| Campaign PF | 1.160 |
| Unit PF | 1.158 |
| Net / stress DD | 6.02 |
| Max open units | 5 |
| Avg campaign | $53.79 |
| Median campaign | $64.75 |
| Best campaign | $6,462.50 |
| Worst campaign | $-2,860.00 |
| Max campaign losing streak | 6 |
| Max campaign winning streak | 16 |

## Yearly Breakdown

|   Year |   Trades |   Units | Net        | Return on ref   | Closed DD   | MTM Stress DD   | Win %   |   PF | Avg Campaign   | Best Campaign   | Worst Campaign   |
|-------:|---------:|--------:|:-----------|:----------------|:------------|:----------------|:--------|-----:|:---------------|:----------------|:-----------------|
|   2021 |      300 |    1493 | $19,443.50 | 259.2%          | $-7,615.00  | $-7,627.50      | 54.7%   | 1.23 | $64.81         | $2,860.00       | $-1,930.00       |
|   2022 |       57 |     285 | $4,228.00  | 56.4%           | $-8,004.50  | $-8,102.00      | 54.4%   | 1.14 | $74.18         | $2,878.00       | $-2,107.50       |
|   2023 |      309 |    1538 | $1,203.50  | 16.0%           | $-9,598.00  | $-9,660.50      | 51.1%   | 1.01 | $3.89          | $2,869.00       | $-1,335.00       |
|   2024 |      382 |    1900 | $16,367.00 | 218.2%          | $-12,234.50 | $-12,372.00     | 52.9%   | 1.13 | $42.85         | $4,822.00       | $-2,045.00       |
|   2025 |      277 |    1378 | $17,958.00 | 239.4%          | $-10,843.00 | $-10,888.00     | 54.2%   | 1.16 | $64.83         | $6,462.50       | $-2,500.00       |
|   2026 |       59 |     292 | $15,241.50 | 203.2%          | $-8,304.50  | $-8,427.00      | 62.7%   | 1.63 | $258.33        | $3,764.50       | $-2,860.00       |

## Exit Reasons

| Exit        |   Units | Net          | Avg Unit   |
|:------------|--------:|:-------------|:-----------|
| eod_close   |    2203 | $343,280.00  | $155.82    |
| runner_stop |    1091 | $-6,642.50   | $-6.09     |
| tp1         |     651 | $97,076.00   | $149.12    |
| tp2         |     261 | $71,218.00   | $272.87    |
| wide_stop   |    2680 | $-430,490.00 | $-160.63   |

## Direction Split

| Direction   |   Units | Net        | Avg Unit   |
|:------------|--------:|:-----------|:-----------|
| Long        |    3517 | $35,901.00 | $10.21     |
| Short       |    3369 | $38,540.50 | $11.44     |

## Read

- This is the best plain MNQ v2b OCO sizing from the sweep by Net/Stress.
- It is runner-heavy: TP1 and TP2 pay, but the three runner units are what lift the edge above the TP-only rows.
- It is a later-stage step after the TP1-only infrastructure rehearsal because max open units rise from 1 to 5 and stress expands materially.

## Files

- `summary.csv` / `SUMMARY_partial.md`
- `mnq_1_1_3_yearly.csv`
- `mnq_1_1_3_exit_reason.csv`
- `mnq_1_1_3_direction.csv`
- `states/mnq_v2b_sizing_S_1_1_3/`