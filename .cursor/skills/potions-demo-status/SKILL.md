---
name: potions-demo-status
description: >-
  Checks status of running potions live/demo paper and OANDA strategies.
  Use for morning checks, heartbeats, open positions, fills, demo daemons,
  PROGRESS.log / run.log review, or when the user asks about live/demo status.
---

# Potions live/demo status

Hub: [`live/demo/README.md`](../../../live/demo/README.md)  
Artifacts live under `live/demo/<run>/` — **not** `live/state/`.

## Environment

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
# Creds: live/demo/.env (gitignored) — never print tokens
```

## Quick inventory

```bash
python3 - <<'PY'
from pathlib import Path
import os
ROOT = Path("live/demo")
for d in sorted(ROOT.iterdir()):
    if not (d / "pidfile").exists():
        continue
    pid = int((d / "pidfile").read_text().strip().splitlines()[0])
    try:
        os.kill(pid, 0); alive = True
    except Exception:
        alive = False
    prog = (d / "PROGRESS.log").read_text(errors="replace").strip().splitlines()
    print(f"{d.name:42} pid={pid} alive={alive}  {prog[-1][:100] if prog else ''}")
PY
```

Also: `ps aux | rg 'potions.live.cli'` and per-demo `python3 -m potions.live.cli <demo>-status` (full list in [reference.md](reference.md)).

## What “healthy” looks like

| Signal | Good | Concern |
|--------|------|---------|
| Process / pidfile | `alive=True` | Dead pidfile / no process |
| Heartbeat age | `PROGRESS.log` / `run.log` updated within ~5–10m | Stale >15–30m |
| Positions | Flat or intentional open qty | Unexpected open + no resting brackets |
| Ticks / bars | Counters advancing (esp. FX / ST+PMC) | Frozen ticks **and** frozen bars mid-session |
| Stream errors | Occasional overnight reconnect then recovery | Repeated ERROR with no later heartbeats |

Index CFDs often freeze `ticks_logged` after cash hours while bars may still persist — check session context before alarming.

## Key files per run

| File | Role |
|------|------|
| `pidfile` | Daemon PID |
| `PROGRESS.log` | Heartbeats, session PnL, errors |
| `run.log` | stdout/stderr |
| `state/fills.csv` | Trade tape |
| `state/positions.csv` | Open if `quantity != 0` |
| `state/orders.csv` | Resting brackets |
| `RUN_META.json` | started_at, routing |

Session ledgers: `live/demo/ungated_paper_results.csv`, `live/demo/ungated_oanda_demo.csv`.

## Report format

Summarize: how many UP, any DOWN, flat vs open, last fill times, today’s stream errors (recovered?), quiet vs active morning.

## Related skills

- `potions-oanda-reconcile` — query OANDA practice / repair local `positions.csv`
- `potions-oanda-pl-attribution` — balance vs resettablePL / fill PL by instrument
- `potions-oanda-live-sim-reconcile` — live fills vs StrategyPlugin replay on demo bars
- `potions-repo-router` — doc routing
- `potions-tracker-docs` — research progress ≠ demo heartbeats
- `potions-git-backup` — do not commit `live/demo/.env` or growing run logs blindly
