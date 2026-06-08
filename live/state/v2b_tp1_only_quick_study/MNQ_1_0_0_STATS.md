# MNQ v2b 1/0/0 TP1-Only Stats

Broker-like `Engine + PaperBroker + StrategyPlugin` replay with 1-tick slippage, stop gap-through, stop-first same-bar ordering, and `$1.50` per closed unit.

## Summary

| Metric | Value |
|---|---:|
| Regime sessions | 1164 |
| Trades | 1306 |
| Units | 1306 |
| Net | $10,084.50 |
| Return on $7.5k reference | 134.5% |
| Closed DD | $-3,095.00 |
| Max MTM / intrabar stress DD | $-3,109.00 |
| Win rate | 54.52% |
| Profit factor | 1.113 |
| Net / stress DD | 3.24 |
| Max open units | 1 |
| Avg trade | $7.72 |
| Median trade | $53.50 |
| Best trade | $722.00 |
| Worst trade | $-572.00 |
| Max losing streak | 6 |
| Max winning streak | 13 |

## Yearly Breakdown

|   Year |   Trades | Net       | Return on $7.5k   | Closed DD   | MTM Stress DD   | Win %   |   PF | Avg Trade   | Best    | Worst    |
|-------:|---------:|:----------|:------------------|:------------|:----------------|:--------|-----:|:------------|:--------|:---------|
|   2021 |      291 | $2,030.00 | 27.1%             | $-1,349.00  | $-1,351.50      | 55.7%   | 1.12 | $6.98       | $317.00 | $-386.00 |
|   2022 |       51 | $4.50     | 0.1%              | $-1,805.00  | $-1,824.50      | 54.9%   | 1    | $0.09       | $402.00 | $-421.50 |
|   2023 |      295 | $-628.50  | -8.4%             | $-2,669.00  | $-2,681.00      | 51.5%   | 0.96 | $-2.13      | $252.00 | $-267.00 |
|   2024 |      349 | $1,868.00 | 24.9%             | $-2,431.00  | $-2,439.50      | 54.4%   | 1.08 | $5.35       | $722.00 | $-409.00 |
|   2025 |      260 | $2,854.50 | 38.1%             | $-3,086.50  | $-3,097.00      | 54.2%   | 1.13 | $10.98      | $435.00 | $-500.00 |
|   2026 |       60 | $3,956.00 | 52.7%             | $-1,567.50  | $-1,592.00      | 65.0%   | 1.8  | $65.93      | $460.00 | $-572.00 |

## Exit Reasons

| Exit      |   Count | Net         | Avg      |
|:----------|--------:|:------------|:---------|
| eod_close |     176 | $696.00     | $3.95    |
| tp1       |     617 | $92,562.50  | $150.02  |
| wide_stop |     513 | $-83,174.00 | $-162.13 |

## Read

- This is the lowest-complexity v2b deployment rehearsal: one entry unit, TP1 exit only, no TP2, no runner, max one open unit.
- It is not the best v2b edge, but it exercises the live plumbing that matters: 1m feed, 5m OR state, OCO entry lifecycle, stop handling, fills, EOD flattening, and restart auditability.
- On a `$7,500` reference stake, the full-window net is about `134.5%`, but individual calendar years vary materially; use the year table for expectations, not the aggregate line alone.

## Files

- `summary.csv`
- `mnq_1_0_0_yearly.csv`
- `mnq_1_0_0_exit_reason.csv`
- `states/mnq_v2b_sizing_S_1_0_0_TP1ONLY/`