# Interim snapshot report — live/state/futures_st_pmc_runner_variants

| field | value |
|---|---|
| status | **IN_PROGRESS** |
| generated_at_utc | 2026-08-23T18:23:22+00:00 |
| completed_required_jobs | 12 / 12 |
| accounting_mode | lot-correct-preferred |
| complete | False |

## Change since prior snapshot

- `= No new promoted strategy`
- `! YM runner variants still active`
- `~ status COMPLETE → IN_PROGRESS`

## Decision summary

- **RETAIN**: MNQ 3R, MNQ 2R→10R, MYM 3R, MYM 2R→10R, NQ 3R, NQ 2R→10R, YM 3R, YM 2R→10R
- **RESEARCH**: MNQ indef, MYM indef, NQ indef, YM indef

### Blocks final judgment

- hub_status=IN_PROGRESS
- 1_active_jobs

### Portfolio action

- MNQ/NQ are execution alternatives / one shared Nasdaq sleeve — not additive independent allocations
- MYM/YM are execution alternatives / one shared Dow sleeve — not additive independent allocations
- No final promotion until required jobs finish.

## Comparable Core Board

Rankable: **yes**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| nq | 3R | $349.5k | -$17.0k | 20.51 | 1128 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mnq | 3R | $23.2k | -$1.2k | 19.38 | 606 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| ym | 3R | $106.4k | -$6.0k | 17.66 | 1762 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| ym | 2R→10R | $313.3k | -$20.6k | 15.22 | 3063 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| nq | 2R→10R | $775.8k | -$55.3k | 14.04 | 1509 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mnq | 2R→10R | $49.9k | -$4.5k | 11.09 | 1104 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mym | 3R | $6.5k | -$634 | 10.28 | 884 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mym | 2R→10R | $20.6k | -$2.1k | 9.76 | 1812 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

## Tested / Not Promoted

Rankable: **no**

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| nq | 3R | $349.5k | -$17.0k | 20.51 | 1128 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mnq | 3R | $23.2k | -$1.2k | 19.38 | 606 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| ym | 3R | $106.4k | -$6.0k | 17.66 | 1762 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| ym | 2R→10R | $313.3k | -$20.6k | 15.22 | 3063 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| nq | 2R→10R | $775.8k | -$55.3k | 14.04 | 1509 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mnq | 2R→10R | $49.9k | -$4.5k | 11.09 | 1104 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mym | 3R | $6.5k | -$634 | 10.28 | 884 | 1 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |
| mym | 2R→10R | $20.6k | -$2.1k | 9.76 | 1812 | 3 | 0 | RETAIN | LOT_CORRECT_ACCOUNTING.csv | — |

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
| mnq | $78.3k | -$31.0k | 45 | 42 | $1571.0k | $78.4k | — | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| mym | $26.0k | -$11.5k | 46 | 40 | $827.9k | $26.1k | — | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| nq | $1197.8k | -$963.2k | 148 | 144 | $29915.9k | $1198.8k | — | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |
| ym | $393.5k | -$260.7k | 108 | 104 | $14141.8k | $394.2k | — | RESEARCH | LOT_CORRECT_ACCOUNTING.csv |

## Diagnostics

- Active jobs (detail in `LATEST_SNAPSHOT.json`): **1**
- Incomplete jobs: **0**
- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.

- **Duplicate sleeve:** MNQ/NQ are execution alternatives / one shared Nasdaq sleeve — not additive independent allocations
- **Duplicate sleeve:** MYM/YM are execution alternatives / one shared Dow sleeve — not additive independent allocations

## Artifacts

- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`
- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`
- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)

