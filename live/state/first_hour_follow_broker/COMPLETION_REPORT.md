# Completion report — live/state/first_hour_follow_broker

| field | value |
|---|---|
| status | **COMPLETE** |
| generated_at_utc | 2026-08-19T04:29:05+00:00 |
| completed_required_jobs | 0 / 0 |
| accounting_mode | lot-correct-preferred |
| complete | True |

## Change since prior snapshot

- `+ Initial snapshot (no prior)`

## Decision summary

- **INCOMPLETE**:  ,  ,  ,  ,  ,  ,  ,  ,  ,  ,  ,  

### Blocks final judgment

- none

### Portfolio action

- none

## Comparable Core Board

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| — | — | | | | | | | | | empty |

## Tested / Not Promoted

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| — | — | | | | | | | | | empty |

## Pending / Non-Comparable

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
|  |  | $176.7k | None |  | 3943 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$1.7k | None |  | 1075 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$51.2k | None |  | 3981 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$114.4k | None |  | 5825 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$181.3k | None |  | 5426 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$16.4k | None |  | 5909 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$384 | None |  | 5908 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$28.4k | None |  | 5856 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$33.4k | None |  | 5744 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | -$4.5k | None |  | 2051 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | $7.7k | None |  | 2213 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing |
|  |  | $0 | None |  | 0 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing; insufficient_sample_units<30 |

## INDEFINITE INVENTORY RESEARCH — NOT RANKABLE

Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin

Forced-flat / reachable figures appear only from `LOT_CORRECT_ACCOUNTING.csv`. Raw archive nets are labeled separately and are not eligible.

| market | forced-flat | reachable stress | max inv | EOY | margin | MTM (sep) | hold med/p90 h | label | source |
|---|---:|---:|---:|---:|---:|---:|---|---|---|

## Diagnostics

- Active jobs (detail in `LATEST_SNAPSHOT.json`): **0**
- Incomplete jobs: **0**
- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.


## Artifacts

- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`
- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`
- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)

