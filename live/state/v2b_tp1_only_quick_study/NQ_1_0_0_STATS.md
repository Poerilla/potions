# NQ v2b 1/0/0 TP1-Only Stats

Broker-like `Engine + PaperBroker + StrategyPlugin` replay with 1-tick slippage, stop gap-through, stop-first same-bar ordering, and `$1.50` per closed unit.

## Summary

| Metric | Value |
|---|---:|
| Regime sessions | 1164 |
| Trades | 1303 |
| Units | 1303 |
| Net | $121,160.50 |
| Return on $75k reference | 161.5% |
| Closed DD | $-32,330.00 |
| Max MTM / intrabar stress DD | $-32,475.00 |
| Win rate | 54.64% |
| Profit factor | 1.137 |
| Net / stress DD | 3.73 |
| Max open units | 1 |
| Avg trade | $92.99 |
| Median trade | $558.50 |
| Best trade | $7,248.50 |
| Worst trade | $-5,696.50 |
| Max losing streak | 6 |
| Max winning streak | 13 |

## Yearly Breakdown

|   Year |   Trades | Net        | Return on $75k   | Closed DD   | MTM Stress DD   | Win %   |   PF | Avg Trade   | Best      | Worst      |
|-------:|---------:|:-----------|:-----------------|:------------|:----------------|:--------|-----:|:------------|:----------|:-----------|
|   2021 |      290 | $22,575.00 | 30.1%            | $-13,126.00 | $-13,151.00     | 55.5%   | 1.14 | $77.84      | $3,178.50 | $-3,821.50 |
|   2022 |       51 | $1,363.50  | 1.8%             | $-17,119.00 | $-17,329.00     | 54.9%   | 1.03 | $26.74      | $4,028.50 | $-4,206.50 |
|   2023 |      293 | $1,125.50  | 1.5%             | $-22,521.50 | $-22,606.50     | 52.2%   | 1.01 | $3.84       | $2,543.50 | $-2,676.50 |
|   2024 |      349 | $24,061.50 | 32.1%            | $-23,562.50 | $-23,632.50     | 54.4%   | 1.1  | $68.94      | $7,248.50 | $-4,076.50 |
|   2025 |      260 | $30,660.00 | 40.9%            | $-30,668.00 | $-30,788.00     | 54.2%   | 1.14 | $117.92     | $4,363.50 | $-4,996.50 |
|   2026 |       60 | $41,375.00 | 55.2%            | $-15,472.00 | $-15,597.00     | 65.0%   | 1.84 | $689.58     | $4,573.50 | $-5,696.50 |

## Exit Reasons

| Exit      |   Count | Net          | Avg        |
|:----------|--------:|:-------------|:-----------|
| eod_close |     171 | $7,583.50    | $44.35     |
| tp1       |     619 | $935,831.50  | $1,511.84  |
| wide_stop |     513 | $-822,254.50 | $-1,602.84 |

## Read

- This is the NQ big-contract mirror of the MNQ TP1-only deployment rehearsal: one entry unit, TP1 exit only, no TP2, no runner, max one open unit.
- The structure is simple, but dollar stress is roughly 10x MNQ. Treat it as a later-stage paper candidate once MNQ plumbing is stable.
- On a `$75,000` reference stake, the full-window net is about `161.5%`; individual calendar years still vary materially.

## Files

- `summary.csv`
- `nq_1_0_0_yearly.csv`
- `nq_1_0_0_exit_reason.csv`
- `states/nq_v2b_sizing_S_1_0_0_TP1ONLY/`