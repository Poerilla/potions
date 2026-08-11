---
name: potions-oanda-reconcile
description: >-
  Queries OANDA practice account and syncs/repairs local live/demo OANDA state.
  Use when reconciling OANDA demos, updating local positions from the broker,
  investigating open-position mismatches, account snapshot, or
  oanda-practice-sync.
---

# OANDA practice → local demo sync

Shared **practice** account feeds all `live/demo/*_oanda` runners. Broker is truth; local CSVs can drift (especially after `reconcile_from_account_details` writes **account-wide** positions into one demo).

## Query + compare (read-only)

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
set -a && source live/demo/.env && set +a   # never print tokens

python3 -m potions.live.cli oanda-practice-sync
# or: python3 -m potions.live.demo.oanda_practice_sync
```

Writes:

- `live/demo/oanda_practice_snapshot/account_snapshot.json`
- `live/demo/oanda_practice_snapshot/REPORT.md`

## Repair stale `positions.csv`

When a demo shows foreign instruments or wrong qty vs live:

```bash
python3 -m potions.live.cli oanda-practice-sync --repair-demo-positions
```

Rewrites each mapped `*_oanda` demo’s `state/positions.csv` to **focus instrument only** (or header-only if flat). Does **not** rewrite `orders.csv` (daemon race) — compare LIVE pending orders in the report to local `orders.csv` manually.

## Focus map

| Demo dir | Focus |
|----------|-------|
| `eurusd_v2b_ungated_oanda` | EURUSD |
| `nas100_v2b_ungated_oanda` | NAS100 |
| `spx500_v2b_ungated_oanda` | SPX500 |
| `us30_v2b_ungated_oanda` | US30 |
| `usdjpy_monday_or_ungated_oanda` | USDJPY |
| `usdjpy_asia_range_london_oanda` | USDJPY |
| `us30_hourly_st_pmc_sl50_tp150_3r_oanda` | US30 |
| `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | NAS100 |
| `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | US30 |
| `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | NAS100 |

## Safety

- Practice only (`OANDA_ENV=practice`); script refuses other envs
- No place/cancel/flatten (use `oanda-emergency-flatten` / demo stop only when user asks)
- After repair, re-check with `potions-demo-status`

## Related skills

- `potions-demo-status` — heartbeats / open inventory
- `potions-repo-router` — `live/demo` vs `live/state`
