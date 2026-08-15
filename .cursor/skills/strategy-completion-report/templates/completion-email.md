# Completion / interim email template (plain text)

Subject: `potions: <hub-short> <completion|INTERIM SNAPSHOT|IN PROGRESS snapshot> — <done>/<total> jobs`

Generated from `LATEST_SNAPSHOT.json` via `live.hub_snapshot` / `live.run_complete_status`.
Never title the mail “completion” when `complete=false` or workers are active.

```text
<INTERIM SNAPSHOT | IN PROGRESS SNAPSHOT | COMPLETION REPORT>
status: …
generated_at_utc: …
completed_required_jobs: N / M
accounting_mode: lot-correct-preferred

CHANGE SINCE PRIOR SNAPSHOT
+ …
= No new promoted strategy
! … still active

DECISION STATE
RETAIN (…): …
RESEARCH (…): …
PENDING_NORMALIZATION (…): …
INCOMPLETE (…): …

BLOCKS FINAL JUDGMENT
- …

PORTFOLIO ACTION REQUIRED: YES|no
- …

Active jobs: N
- MARKET: variant, status/progress

Incomplete jobs: N
- …

COMPARABLE CORE BOARD (rankable only if all gates pass)
…

INDEFINITE INVENTORY RESEARCH — NOT RANKABLE
MARKET  forced-flat=… | reachable stress=… | max inv=… | EOY open=… | margin=…

PENDING / NON-COMPARABLE
- … [reason]

Hub: live/state/<hub>/
Report: COMPLETION_REPORT.md
Snapshot: LATEST_SNAPSHOT.json
```

Keep under ~50 lines for phone readability. Numbers come from snapshot/summary — not invented.
PID/host/command stay in hub JSON only.
