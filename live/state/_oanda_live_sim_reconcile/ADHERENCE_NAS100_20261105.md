# NAS100 clean-break adherence + duplicate-daemon fix (2026-11-05)

Book: `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda`, account `-003`. Window: 2026-10-30 → 2026-11-05.

## Finding

Two daemons ran on the same output/state directory and the same OANDA account from 2026-11-02 16:59 NY:
pid 203890 (started Sep 22, orphaned — no pidfile) and pid 1580741 (Nov 2 restart). The Asia-range book had
the same defect (pid 659107 from Oct 22 on old code + pid 1578721 from Nov 2), not yet harmful.

How it happened: any runner exiting called `_remove_pidfile`, deleting the pidfile even when it belonged to a
different live process. The failed 16:56 missing-token restart on Nov 2 removed the pidfile, so the 16:59
spawn's "already running?" check saw nothing and started a second daemon.

Effect on Nov 4 (-003):
- Daemon B's entry was `routing_blocked`; daemon A's entry filled (buy 10 @ 28706.5, 09:45).
- Both share `positions.csv` / strategy state. At 09:50 the plugin decided `flatten` (close back inside range),
  and at 15:55 `eod_close`, but the evaluating process saw position 0 → no exit order.
- 00:05 NY Nov 5: containment reconcile restored qty 10 in both → each sent `eod_close` (prior-session flatten)
  → long closed −$5,587 and a **stray short 10 @ 28147.5** opened.

## Adherence (live vs plugin replay on stored bars, since Oct 30)

| Day | Live | Sim | Verdict |
|---|---|---|---|
| Oct 30 | entry 09:58 / close_back_into_range 10:10, −$549 | 09:55 / 10:05, −$495 | same 5m bar |
| Nov 2 | entry + 2 adds, trail_stop 30 @ 28627.9, −$1,976 (4th add rejected INSUFFICIENT_MARGIN under old cap 40) | same path, −$1,983 | match |
| Nov 3 | entry / failed_clean_close, −$206 | same bar, −$220 | match |
| **Nov 4** | **held overnight; eod 00:05 −$5,587; stray short −$673** | close_back_into_range 09:50, −$688 | **violation (duplicate daemons)** |

Entries 4/4 (2 exact, 2 in the same 5m signal bar); no config drift. Cost of the violation vs rules ≈ **−$5,572**.

## Fix (done 2026-11-05 08:35–08:37 NY)

1. Backed up state tables (`state_backup_20261105_pre_dedup/`), SIGTERM'd all four daemons (NAS ×2, Asia ×2).
2. Closed the stray short on `-003` via OANDA position close (tx 301, buy 10 @ 28214.8, pl −$673). Account flat.
3. Local NAS state set to broker truth: `positions.csv` qty 0; manual-close fill row 301 (`manual_flatten`);
   today's strategy state reset to a fresh session (the prior-session flatten had set `done=True`, which would
   have skipped today's session).
4. Code: `acquire_instance_lock()` (flock on `<output_root>/daemon.lock`, held for process life) in the shared
   v2b loop and the NAS clean-break, Asia-range, Monday OR runners — a second runner logs
   `REFUSING start` and exits 3 before touching state. `_remove_pidfile` only removes its own pid.
   Test `live/tests/test_demo_instance_lock.py`; verified live (foreground launch refused, exit 3).
5. Restarted one daemon each: NAS pid 2042476 (-003, reconcile flat, stream up), Asia pid 2042569 (-004, flat,
   shadow book 147 obs, no double appends).

Monday OR (pid 3698979, single instance since Oct 1) gets the lock on its next restart.

Reconciler: `reconcile_oanda_demos.py --since <iso>` added to score across restarts.
