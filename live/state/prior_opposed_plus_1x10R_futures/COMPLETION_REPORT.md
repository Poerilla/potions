# Interim snapshot report — live/state/prior_opposed_plus_1x10R_futures

| field | value |
|---|---|
| status | **PARTIAL** |
| generated_at_utc | 2026-08-09T22:43:42+00:00 |
| completed_required_jobs | 0 / 9 |
| accounting_mode | lot-correct-preferred |
| complete | False |

## Change since prior snapshot

- `+ Initial snapshot (no prior)`

## Decision summary

- **INCOMPLETE**: NQ , MNQ , YM 

### Blocks final judgment

- hub_status=PARTIAL
- 12_incomplete_jobs

### Portfolio action

- MNQ/NQ are execution alternatives / one shared Nasdaq sleeve — not additive independent allocations
- No final promotion until required jobs finish.

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
| nq |  | $1618.3k | None |  | 0 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing; insufficient_sample_units<30 |
| mnq |  | $156.2k | None |  | 0 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing; insufficient_sample_units<30 |
| ym |  | $344.0k | None |  | 0 | None | 0 | INCOMPLETE | summary.csv_raw | variant_incomplete_or_missing_audit; reachable_stress_missing; insufficient_sample_units<30 |

## INDEFINITE INVENTORY RESEARCH — NOT RANKABLE

Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin

Forced-flat / reachable figures appear only from `LOT_CORRECT_ACCOUNTING.csv`. Raw archive nets are labeled separately and are not eligible.

| market | forced-flat | reachable stress | max inv | EOY | margin | MTM (sep) | hold med/p90 h | label | source |
|---|---:|---:|---:|---:|---:|---:|---|---|---|

## Diagnostics

- Active jobs (detail in `LATEST_SNAPSHOT.json`): **0**
- Incomplete jobs: **12**
- Raw metrics remain in `summary.csv` / MTM audits; eligible metrics note `metric_source`.

- **Duplicate sleeve:** MNQ/NQ are execution alternatives / one shared Nasdaq sleeve — not additive independent allocations
- **Duplicate sleeve:** MNQ/NQ are execution alternatives / one shared Nasdaq sleeve — not additive independent allocations

## Exit attribution (10R / EOD-survivor)

| market / id | book label | TP1 | TP2 | hard stop | BE stop | EOD | true 10R | 10R hits | moonshot? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| mnq | v2b S_1_1_3 + 1 BE-protected long-horizon / EOD-survivor runner | $36.1k | $28.0k | -$106.0k | -$2.7k | $199.1k | $1.7k | 1 (0.0%) | no |
| nq | v2b S_1_1_3 + 1 BE-protected long-horizon / EOD-survivor runner | $370.4k | $293.4k | -$1045.9k | -$22.1k | $2005.9k | $16.6k | 1 (0.0%) | no |
| ym | v2b S_1_1_3 + 1 BE-protected long-horizon / EOD-survivor runner | $134.4k | $87.7k | -$486.6k | -$13.1k | $621.5k | $0 | 0 (0.0%) | no |

## Artifacts

- `LATEST_SNAPSHOT.json`, `snapshots/SNAPSHOT_*.json`
- `COMPLETION_EMAIL.txt`, `SNAPSHOT_CHANGELOG.txt`
- `STATUS.json` / `RUN_COMPLETE.json` (compat shim)

