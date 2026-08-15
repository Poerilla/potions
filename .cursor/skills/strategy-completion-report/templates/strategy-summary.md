# COMPLETION_REPORT.md template

```markdown
# <Completion report | Interim snapshot report> — <hub>

| field | value |
|---|---|
| status | COMPLETE \| IN_PROGRESS \| PARTIAL \| FAILED |
| generated_at_utc | … |
| completed_required_jobs | N / M |
| accounting_mode | lot-correct-preferred |
| complete | true\|false |

## Change since prior snapshot
- …

## Decision summary
- **PROMOTE / RETAIN / RESEARCH / REJECT / PENDING_*** / **INSUFFICIENT_SAMPLE / INCOMPLETE / NOT_RANKABLE**: …

### Blocks final judgment
- …

### Portfolio action
- …

## Comparable Core Board
Rankable: yes only if every row passed gates
(variant_complete, usd_normalized, reachable_stress, lot_correct where applicable,
sufficient_sample, eoy flat for flat books, no unresolved accounting warning;
indefinite excluded)

| market | book | net | stress | N/S | units | max | EOY | label | source | reasons |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|

## Tested / Not Promoted
…

## Pending / Non-Comparable
…

## INDEFINITE INVENTORY RESEARCH — NOT RANKABLE
Headline: Forced-flat net | reachable full-stack stress | max inventory | EOY open lots | margin

## Diagnostics
- Active / incomplete job counts
- Raw vs corrected metric sources (`summary.csv` vs `LOT_CORRECT_ACCOUNTING.csv` / USD-norm)
```

Generate with: `python -m live.hub_snapshot --hub <hub> --write`
