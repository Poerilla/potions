---
name: potions-instrument-deep-check
description: >-
  Runs year-by-year net/stress/N/S and NQ-style robustness deep-checks on a
  single potions instrument/strategy book, plus entry/exit timing and win/loss
  chart samples. Use when auditing one symbol after a sweep, asking for yearly
  breakdown, net/stress by year, 100k compound returns, full SL counts, TP vs
  EOD exit mix, or 50 wins/50 losses charts with HTML email.
---

# Potions instrument deep-check

**Platform calculates; agent emails HTML; human decides promote.**

Use after a strategy hub finishes and one instrument looks interesting (e.g.
USDJPY on London KZ sweep or Asia-range v2b).

## Inputs

| Kind | State root example |
|------|--------------------|
| Broker-like plugin | `live/state/<hub>/states/<strategy_id>/` with `fills.csv` + `equity_curve.csv` |
| Research sim | same layout with `trades.csv` only (London sweep) |

Read `metrics.json` for symbol/quote/book. JPY books must stay USD-normalized (`/110`).

## Procedure

1. Deep-check (yearly + robustness + timing):

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
python -m live.instrument_deep_check \
  --state-root live/state/<hub>/states/<strategy_id> \
  --label "<human label>" \
  --email
```

Add `--prior-opposed` only when gap/OR columns exist (NQ-style prior-opposed).
Skip for London KZ / Asia-range clocks.

Artifacts → `live/state/<hub>/deep_check/<strategy_id>/`:

- `YEARLY.md` / `yearly_breakdown.csv` — net, stress, N/S, $100k compound return/year
- `ROBUSTNESS_AUDIT.md` — concentration, rolling 50, exits, recovery, ATR/range quartiles
- `entry_hour_dist.csv` / `exit_hour_dist.csv` + timing charts
- `EMAIL.html` + `EMAIL.txt` (HTML multipart via `notify_email`)

2. Win/loss charts (50/50 default):

```bash
python -m live.instrument_winloss_charts \
  --state-root live/state/<hub>/states/<strategy_id> \
  --wins 50 --losses 50 --email
```

Artifacts → `live/state/<hub>/winloss_charts/<strategy_id>/` (`INDEX.md`, `charts/`, zip).

3. Always email (skill `potions-job-email`). Prefer `--email` on both drivers.
   HTML multipart: `send_email(..., html=..., attachments=[...])`.

## What “good” looks like in the yearly board

- Report every traded year: **net**, **stress**, **N/S**, **return on start equity** (compound from $100k at year 1).
- Call out weakest N/S year and full-initial-SL share.
- Timing: modal entry/exit hours; % hit TP vs % EOD flatten vs full SL.

## Related

- `live/nq_v2b_prior_opposed_robustness_audit.py` — futures prior-opposed reference
- `potions-job-email` — notify on complete/crash
- `strategy-completion-report` — hub-wide promote boards (not per-instrument forensics)
