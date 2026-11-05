---
name: potions-demo-start-stop
description: >-
  Starts, stops, and restarts potions live/demo daemons (OANDA practice and
  paper) under the singleton locks: broker-flat pre-flight, session windows,
  demo-restart, -stop, first start with --daemon, ownership registry,
  post-checks (singleton audit, SINGLETON claimed, stream, reconcile), email
  and ledger. Use every time a demo daemon is started, stopped, restarted,
  redeployed after a code change, rotated to another account, or when the
  user says start/stop/restart/bounce/relaunch a demo or strategy.
---

# Start / stop / restart demo daemons

**One rule:** one runner per output folder, per strategy, and per OANDA account+instrument. `live/demo/singleton.py` enforces it at start, and a second copy exits **3** with `REFUSING start`. Never work around a refusal. Find out who holds the lock instead.

Setup for every command (never print `.env`):

```bash
cd /home/tester/hsm
set -a && source potions/live/demo/.env && set +a
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
CLI="python3 -m potions.live.cli"
CFG=/home/tester/hsm/potions/live/demo/oanda_account_configs
```

## Books

| Book (demo dir) | Account | Start command | Config | Trades (NY) |
|---|---|---|---|---|
| `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | `-003` | `demo-nas100-clean-break-trail-oanda` | `nas100_clean_break_trail_003.json` | RTH 09:30–15:55 |
| `usdjpy_asia_range_london_oanda` | `-004` | `demo-usdjpy-asia-range-oanda` | `usdjpy_asia_range_004.json` | 03:00–11:59 |
| `usdjpy_monday_or_ungated_oanda` | `-005` | `demo-usdjpy-monday-or-oanda` | `usdjpy_monday_or_005.json` | Mon OR; Tue–Fri; flat Fri 15:59 |
| `usdjpy_monthly_orb_fbo_oanda` | `-006` | `demo-usdjpy-monthly-fbo-oanda` | `usdjpy_monthly_fbo_006.json` | multi-day |
| yearly ORB | `-002` | `demo-yearly-orb-oanda` | — | multi-month |

`-001` stays dormant. The owner of each account+instrument is listed in `live/demo/oanda_account_ownership.json`, and `TOP3_ACCOUNT_MAP.md` explains it.

## 1. Pre-flight (always)

```bash
$CLI demo-singleton-audit --no-email     # must show no ALARM before you touch anything
python3 -c "from pathlib import Path; from potions.live.demo.singleton import broker_flat, DEMO_DIR; print(broker_flat(DEMO_DIR/'<book>'))"
```

- Restart only when the account is **flat** with **0 pending orders**, and outside the book's trading window. Exception: the session is already `done` in `state/strategy_state.csv` and the account is flat.
- If the book has an open trade, wait, or queue the restart with `--when-flat` (below). Never bounce mid-trade unless the user says so.
- If the audit shows an `ALARM`, report it and let the user decide what to stop. Don't kill anything on your own.

## 2. Restart (normal case: code change, config change, stale process)

```bash
$CLI demo-restart <book>                                             # flat now
$CLI demo-restart <book> --not-before 12:05 --when-flat --email      # queue (run with setsid nohup … &)
```

`demo-restart` SIGTERMs every runner on the folder and waits for the locks to free (SIGKILL after `--stop-timeout`). It then relaunches the **same argv** with `.env` loaded, writes `pidfile`, and checks that exactly one process holds `daemon.lock`. Exit 0 means OK.

## 3. Stop (take a book offline)

```bash
$CLI demo-<book-cmd>-stop                     # e.g. demo-usdjpy-asia-range-oanda-stop
$CLI demo-singleton-audit --no-email          # confirm no runner left on that folder
```

`-stop` signals only the pid in `pidfile`. If the audit still lists a runner on that folder, report it.

## 4. First start / start after stop

```bash
$CLI demo-usdjpy-asia-range-oanda --daemon --oanda-config "$CFG/usdjpy_asia_range_004.json"
```

- Always pass an **absolute** `--oanda-config` for OANDA books. Asia must use `usdjpy_asia_range_004.json`.
- A new strategy on an account, or an account rotation, needs the registry row in `oanda_account_ownership.json` **first**. Without it the runner refuses with "has no owner".
- `Already running as pid …` or `REFUSING start` means it is already up. Use `demo-restart` instead.

## 5. Post-checks (every start/restart)

1. `$CLI demo-singleton-audit --no-email` shows every book `lock=True` and no `ALARM`.
2. `PROGRESS.log` should contain, in order: `SINGLETON claimed … routes_orders=True`, `STARTED`, `OANDA reconcile … open_orders=0 positions=0` (when flat), `containment bootstrap … ok=True`, `STREAM connected status=200`, then a heartbeat. One or two `stream_open … 401` lines that end in `STREAM connected` are a known transient.
3. `tr '\0' ' ' </proc/<pid>/cmdline` shows the correct `--oanda-config` account.

## 6. Record

- Add a line to `live/PROGRESS.log` (book, old→new pid, reason). Add to `live/demo/ADHERENCE_ISSUES.md` if it fixed an issue.
- Email a short summary (`potions-job-email`) and add a ledger row (`potions-run-ledger`, `run_class="audit"`) when the restart was part of a fix or rollout.

## Never

- Delete or edit `pidfile`, `daemon.lock`, or `live/demo/.locks/*`.
- Use `kill` followed by `--daemon` as a restart. That bypassed the old pidfile check and caused the 2026-11-04 NAS/Asia double daemons.
- Start a second copy "to test". Use `--max-ticks` with a tmp `--output-root` on a **paper** command instead.
- Change shadow logic or `strategy_state.csv` while restarting (Asia shadow is frozen by design).

## Related

- `potions-demo-status`: health and heartbeats before and after.
- `potions-oanda-live-sim-reconcile`: adherence after a restart.
- `potions-oanda-reconcile`: broker vs local positions when the account isn't flat.
- `live/demo/README.md`: the "One runner per strategy" section.
