# Interim snapshot report — live/state/fx_index_metals_st_pmc_runner_variants

| field | value |
|---|---|
| status | **IN_PROGRESS** |
| generated_at_utc | 2026-08-27T00:05:37+00:00 |
| completed_required_jobs | 21 / 21 |
| accounting_mode | lot-correct-preferred |
| complete | False |

## Change since prior snapshot

- `= No new promoted strategy`
- `! XAUUSD runner variants still active`
- `~ status COMPLETE → IN_PROGRESS`

## Decision summary

- **RETAIN**: NAS100 3R, USDJPY 3R, XAUUSD 3R, XAUUSD 2R→10R
- **RESEARCH**: EURUSD indef, GBPUSD indef, NAS100 indef, XAGUSD indef, XAUUSD indef
- **PENDING_NORMALIZATION**: AUDJPY 3R, AUDJPY 2R→10R, AUDJPY indef, USDJPY 2R→10R, USDJPY indef
- **INSUFFICIENT_SAMPLE**: XAGUSD 3R, XAGUSD 2R→10R
- **NOT_RANKABLE**: EURUSD 3R, EURUSD 2R→10R, GBPUSD 3R, GBPUSD 2R→10R, NAS100 2R→10R

### Blocks final judgment

- hub_status=IN_PROGRESS
- 1_active_jobs
- usd_normalization_pending:audjpy,usdjpy

### Portfolio action

- No final promotion until required jobs finish.
- Normalize JPY results before cross-market ranking.

## Comparable Core Board

Rankable: **yes**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| nas100 | 3R | $15.2k | -$778 | 19.56 | 856 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| xauusd | 2R→10R | $278.1k | -$167.9k | 1.66 | 129 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| usdjpy | 3R | $30.4k | -$19.5k | 1.56 | 1372 | 1 | 0 | RETAIN | FAIR_3R_USD_NORMALIZED.md | — |
| xauusd | 3R | $77.3k | -$92.9k | 0.83 | 181 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

## Tested / Not Promoted

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| nas100 | 3R | $15.2k | -$778 | 19.56 | 856 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| xauusd | 2R→10R | $278.1k | -$167.9k | 1.66 | 129 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| usdjpy | 3R | $30.4k | -$19.5k | 1.56 | 1372 | 1 | 0 | RETAIN | FAIR_3R_USD_NORMALIZED.md | — |
| xauusd | 3R | $77.3k | -$92.9k | 0.83 | 181 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

## Pending / Non-Comparable

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| audjpy | 3R | $9171.1k | -$1163.0k | 7.89 | 1334 | 1 | 1 | PENDING_NORMALIZATION | LOT_CORRECT_ACCOUNTING.csv | native_jpy_not_usd_normalized; eoy_open_units_nonzero |
| audjpy | 2R→10R | $9825.6k | -$4798.9k | 2.05 | 1257 | 3 | 3 | PENDING_NORMALIZATION | LOT_CORRECT_ACCOUNTING.csv | native_jpy_not_usd_normalized; eoy_open_units_nonzero |
| eurusd | 3R | $64.4k | -$21.4k | 3.01 | 1402 | 1 | 1 | NOT_RANKABLE | LOT_CORRECT_ACCOUNTING.csv | eoy_open_units_nonzero |
| eurusd | 2R→10R | $121.2k | -$67.3k | 1.80 | 1041 | 3 | 1 | NOT_RANKABLE | LOT_CORRECT_ACCOUNTING.csv | eoy_open_units_nonzero |
| gbpusd | 3R | $108.1k | -$13.3k | 8.12 | 1754 | 1 | 1 | NOT_RANKABLE | LOT_CORRECT_ACCOUNTING.csv | eoy_open_units_nonzero |
| gbpusd | 2R→10R | $101.4k | -$41.1k | 2.47 | 1722 | 3 | 2 | NOT_RANKABLE | LOT_CORRECT_ACCOUNTING.csv | eoy_open_units_nonzero |
| nas100 | 2R→10R | $34.1k | -$3.1k | 11.13 | 1347 | 3 | 1 | NOT_RANKABLE | LOT_CORRECT_ACCOUNTING.csv | eoy_open_units_nonzero |
| usdjpy | 2R→10R | $2801.2k | -$6519.9k | 0.43 | 1086 | 3 | 1 | PENDING_NORMALIZATION | LOT_CORRECT_ACCOUNTING.csv | native_jpy_not_usd_normalized; eoy_open_units_nonzero |
| xagusd | 3R | $68.7k | -$58.6k | 1.17 | 1 | 1 | 1 | INSUFFICIENT_SAMPLE | LOT_CORRECT_ACCOUNTING.csv | insufficient_sample_units<30; eoy_open_units_nonzero |
| xagusd | 2R→10R | $206.2k | -$175.8k | 1.17 | 3 | 3 | 3 | INSUFFICIENT_SAMPLE | LOT_CORRECT_ACCOUNTING.csv | insufficient_sample_units<30; eoy_open_units_nonzero |

## INDEFINITE INVENTORY RESEARCH — NOT RANKABLE

Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin

Forced-flat / reachable figures appear only from `LOT_CORRECT_ACCOUNTING.csv`. Raw archive nets are labeled separately and are not eligible.

| market | forced-flat | reachable stress | max inv | EOY | margin | MTM (sep) | hold med/p90 h | label | source |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| audjpy | $16382.5k | -$24697.1k | 178 | 177 | $1552647.3k | $16400.5k | 48 / 311 | PENDING_NORMALIZATION | LOT_CORRECT_ACCOUNTING.csv |
| eurusd | $339.5k | -$228.4k | 239 | 238 | $28685.7k | $340.1k | 47 / 269 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| gbpusd | $220.6k | -$267.6k | 212 | 212 | $31399.6k | $221.1k | 29 / 192 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| nas100 | $54.3k | -$22.6k | 74 | 70 | $1019.1k | $54.4k | 7 / 143 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| usdjpy | $14355.2k | -$42280.0k | 199 | 195 | $2282912.9k | $14375.0k | 48 / 275 | PENDING_NORMALIZATION | LOT_CORRECT_ACCOUNTING.csv |
| xagusd | $15.1k | -$175.8k | 3 | 3 | $215.5k | $15.1k | 8655 / 8722 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| xauusd | $995.9k | -$2006.3k | 103 | 94 | $21206.1k | $996.1k | 373 / 2628 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |

## Diagnostics

- Active jobs (detail in `LATEST_SNAPSHOT.json`): **1**
- Incomplete jobs: **0**
- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.


## Artifacts

- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`
- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`
- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)

