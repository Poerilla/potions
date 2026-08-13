---
name: potions-intraday-condition-profile
description: >-
  Profiles calendar / HTF / 5m conditions against broker-like campaign outcomes
  for running intraday potions books (Monday OR, Asia-range, v2b, London
  prior-opposed, ST+PMC). Use when asking which day-of-week, week-of-month,
  hourly RSI/OBV, 5m MA cross, ATR quartile, or prior day/week/month range-half
  conditions lift win rate or avg net — diagnostic only, not a promotion gate.
---

# Potions intraday condition profile

Hub: [`live/state/intraday_condition_profile/`](../../../live/state/intraday_condition_profile/)  
Driver: `live/intraday_condition_profile.py`

Joins research/broker-like **campaign** tapes (aligned to live intradaily demos)
to causal asof features and ranks bucket lift vs each book’s baseline.

## Environment

```bash
cd /home/tester/hsm/potions
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
```

## Run

```bash
# all default books + email
python -m live.intraday_condition_profile --email

# one book
python -m live.intraday_condition_profile --book usdjpy_monday_or --email

# raise min bucket N (default 40)
python -m live.intraday_condition_profile --min-n 60 --email
```

Always pass `--email` (skill `potions-job-email`). Artifacts → hub root.

## Features (causal asof at entry)

| Feature | Definition |
|---------|------------|
| Day of week / week of month / NY hour | Calendar from entry ts |
| 5m MA state + cross | SMA9/21; align = state/cross with trade side |
| Hourly RSI14 | Buckets + with/against/neutral vs side |
| Hourly OBV × MA20 | Above/below; align vs trade |
| Daily ATR14 | Quartiles within book |
| Prior day/week/month range half | **aligned** = long in lower half / short in upper half; else opposed |

## Default books

Research fills (not thin live demo tapes), keyed in `DEFAULT_BOOKS`:

- Monday OR: EURUSD / USDJPY / US30
- USDJPY Asia-range London filtered `S_3_1_3`
- EURUSD v2b ungated; NAS100 London ungated (proxy for live NAS100 v2b)
- US30 London prior-opposed
- Hourly ST+PMC 50/150 3r: NAS100 / US30 / EURUSD

SPX500 omitted (no long `fx/` 1m series). Yearly ORB is multi-day — out of scope.

## What “notable” means

Heuristic (not a gate): bucket n≥40, **both** WR lift and avg-net lift positive, and
(|z_WR|≥1.64 **or** avg lift ≥35% of |baseline avg|).

Cross-book notables = same condition/bucket clearing that bar on ≥1 book;
prefer signals that repeat across families.

## Report format

1. Open hub `SUMMARY.md` + `EMAIL.txt`.
2. Lead with **cross-book** repeats (Fri/Thu, RSI extremes / against-side, ATR q4, week-opposed, etc.).
3. Call out strongest **per-book** dual-lift rows with n and z_WR.
4. Reminder: multiple comparisons → hypotheses only; do not promote filters from this alone.
   Follow with null/OOS / `potions-quick-backtest` if anything looks actionable.

## Artifacts

| File | Role |
|------|------|
| `SUMMARY.md` | Books, cross-book notables, per-book top buckets |
| `notables.csv` / `*_buckets.csv` | Full bucket stats |
| `*_campaigns.csv` / `all_campaigns.csv` | Annotated campaign rows |
| `baselines.json` | Per-book n / WR / avg / net |
| `EMAIL.txt` | Phone summary |

## Related

- `potions-job-email` — always notify on complete/crash
- `potions-futures-intraday-hp-sizeup` — futures 1.25× HP nulls + Tier A/B/C plan
- `potions-quick-backtest` — broker-like replay if testing a candidate filter
- `potions-instrument-deep-check` — yearly robustness on one book
- `potions-oanda-live-sim-reconcile` — live vs sim tape (ops, not this profile)
- `potions-repo-router` — task routing
