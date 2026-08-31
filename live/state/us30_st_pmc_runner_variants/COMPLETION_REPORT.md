# Completion report — live/state/us30_st_pmc_runner_variants

| field | value |
|---|---|
| status | **COMPLETE** |
| generated_at_utc | 2026-08-23T05:03:54+00:00 |
| completed_required_jobs | 3 / 3 |
| accounting_mode | lot-correct-preferred |
| complete | True |

## Change since prior snapshot

- `= No new promoted strategy`

## Decision summary

- **RETAIN**: US30 3R, US30 2R→10R
- **RESEARCH**: US30 indef

### Blocks final judgment

- none

### Portfolio action

- none

## Comparable Core Board

Rankable: **yes**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| us30 | 2R→10R | $13.3k | -$9.1k | 1.47 | 1908 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| us30 | 3R | -$982 | -$4.6k | -0.21 | 1017 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

## Tested / Not Promoted

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| us30 | 2R→10R | $13.3k | -$9.1k | 1.47 | 1908 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| us30 | 3R | -$982 | -$4.6k | -0.21 | 1017 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

## Pending / Non-Comparable

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| — | — | | | | | | | | | empty |

## INDEFINITE INVENTORY RESEARCH — NOT RANKABLE

Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin

Forced-flat / reachable figures appear only from `LOT_CORRECT_ACCOUNTING.csv`. Raw archive nets are labeled separately and are not eligible.

| market | forced-flat | reachable stress | max inv | EOY | margin | MTM (sep) | hold med/p90 h | label | source |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| us30 | $9.2k | -$34.3k | 77 | 72 | $2569.7k | $9.3k | 1 / 27 | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |

## Diagnostics

- Active jobs (detail in `LATEST_SNAPSHOT.json`): **0**
- Incomplete jobs: **0**
- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.


## Artifacts

- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`
- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`
- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)

