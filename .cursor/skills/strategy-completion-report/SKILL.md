---
name: strategy-completion-report
description: >-
  Reads completed potions strategy-hub artifacts (summary.csv, MTM audits,
  RUN_COMPLETE.json), classifies promote/retain/research/reject/pending, writes
  hub completion reports, and drafts a short phone email. Use when a backtest
  batch finishes, RUN_COMPLETE.json appears, the user asks for a completion
  summary, or headless `agent -p` invokes this skill after a job.
---

# Strategy completion report

**Platform calculates; agent explains; human approves promotion.**

Do **not** invent metrics from progress logs. Read facts from artifacts only.

## When to use

- FX/index/metals / US30 / futures ST+PMC runner batch finished
- `live/state/<hub>/RUN_COMPLETE.json` present
- User asks for completion summary / promote stance after a sweep
- Headless: `scripts/run_completion_report_agent.sh <hub>`

## Hard rules (refuse to promote if violated)

1. Never compare **native JPY** nets to **USD-normalized** nets on the same board.
2. Keep **indefinite / inventory** sleeves off rankable N/S boards (report in a separate panel).
3. Prefer **lot-correct / reachable-stress** figures when both raw and lot-correct exist.
4. Refuse promotion if coverage, lot matching, fill realism, or currency normalization is incomplete.
5. Do not edit live/demo daemons or push git unless the user explicitly asks.
6. Decision-critical math stays in Python (`live/format_job_summary.py`, hub `summary.csv`). Agent interprets and documents.

## Inputs (read in order)

1. Hub path (arg or detect): e.g. `live/state/fx_index_metals_st_pmc_runner_variants/`
2. `RUN_COMPLETE.json` (if present) — markets, variants, accounting flags, exit codes
3. `summary.csv` + `SUMMARY.md`
4. Per-market `audits/*/reports/MTM_AUDIT.md` and `LOT_CORRECT_ACCOUNTING.md` / `FAIR_3R_USD_NORMALIZED.md` when present
5. Length-sweep hub if relevant: `live/state/st_pmc_runner_length_sweep/`
6. Prior stance: `mnq/case_studies/STRATEGY_TRACKER.md` (ST+PMC section)

## Procedure

1. Run deterministic snapshot (do not hand-compute N/S):

   ```bash
   export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
   python -m live.hub_snapshot --hub <hub> --write
   # or
   python -m live.run_complete_status --hub <hub> --write --email-body
   ```

   Artifacts: `LATEST_SNAPSHOT.json`, `COMPLETION_EMAIL.txt`, `COMPLETION_REPORT.md`,
   `SNAPSHOT_CHANGELOG.txt`. Email title is INTERIM/IN PROGRESS unless `complete=true`.

2. For each market × variant, classify (labels from snapshot):

   | Class | Meaning |
   |---|---|
   | **PROMOTE** | Human-approved only; never auto-assigned by snapshot |
   | **RETAIN** | Passed comparable-core gates; keep as research champion |
   | **RESEARCH** | Interesting inventory / non-board (e.g. indefinite with accounting) |
   | **REJECT** | Worse than baseline on rankable terms (agent/human) |
   | **PENDING_NORMALIZATION** | JPY/native USD bridge missing for this variant |
   | **PENDING_ACCOUNTING** | Lot-correct / reachable stress missing |
   | **INSUFFICIENT_SAMPLE** | Too few trades/units |
   | **INCOMPLETE** | Variant still running / missing audit |
   | **NOT_RANKABLE** | Failed eligibility gates |

3. Generate outputs into the hub (see templates/):

   - `COMPLETION_REPORT.md` — decision summary + boards
   - `LATEST_SNAPSHOT.json` / `STATUS.json` — machine-readable classifications
   - Short plain-text email via:

     ```bash
     python -m live.notify_email --subject "potions: <hub> interim/completion" --body-file <hub>/COMPLETION_EMAIL.txt
     ```

   Prefer `python -m live.hub_snapshot --hub <hub> --write --email` when notifying.
4. Doc sync (only if classifications are firm — use `potions-tracker-docs`):

   - Hub `SUMMARY.md` link to `COMPLETION_REPORT.md`
   - `live/PROGRESS.log` one-liner
   - `STRATEGY_TRACKER.md` / `CHANGE_LOG.md` **only** on promote or explicit demote

5. Stop. Do not auto-commit unless asked.

## Output shape

Follow [`templates/strategy-summary.md`](templates/strategy-summary.md) and
[`templates/completion-email.md`](templates/completion-email.md).

Required sections in `COMPLETION_REPORT.md`:

1. One-paragraph **decision summary**
2. **Rankable comparable leaderboard** (3R and 2R→10R only; USD-normalized when FX/JPY)
3. **Research / inventory panel** (indef, sweeps, notes)
4. **Exceptions panel** (missing audits, currency, lot-correct gaps, validation fails)

## Headless CLI

```bash
# After job writes RUN_COMPLETE.json:
scripts/run_completion_report_agent.sh live/state/fx_index_metals_st_pmc_runner_variants

# Or manually:
agent -p --force "Use the strategy-completion-report skill. Process
live/state/fx_index_metals_st_pmc_runner_variants and produce the report."
```

Cloud async (from an interactive `agent` session): prefix the same prompt with `&`.

## Related skills

- `potions-tracker-docs` — tracker / CHANGE_LOG / PROGRESS
- `potions-repo-router` — where hubs live
- `potions-causality-audit` — only if promoting a Tier-1 change that needs audit rows
