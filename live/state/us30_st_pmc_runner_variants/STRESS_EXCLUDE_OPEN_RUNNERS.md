# Stress without open-runner MTM (post-process)

Recomputed from existing `fills.csv` + hourly bars. **No replay re-run.**

Rule: units with `entry_reason` starting `runner_entry` are excluded from **open** MTM;
their P&L still enters **realized** when they close (target / runner_stop / year_end_flatten).
TP1 (`entry`) units remain in open stress.

| variant | mode | net | stress | N/S | max open (stress) | max open (all) |
|---|---|---:|---:|---:|---:|---:|
| `sl50_tp150_3r_1mfill` | full_open_mtm | $19028 | $-907 | 20.97 | 1 | 1 |
| `sl50_tp150_3r_1mfill` | exclude_open_runners | $19028 | $-907 | 20.97 | 1 | 1 |
| `sl50_tp150_runners_2r_10r` | full_open_mtm | $56111 | $-2867 | 19.57 | 3 | 3 |
| `sl50_tp150_runners_2r_10r` | exclude_open_runners | $56111 | $-2072 | 27.08 | 1 | 3 |
| `sl50_tp150_runners_2r_indef` | full_open_mtm | $191517 | $-73531 | 2.60 | 65 | 65 |
| `sl50_tp150_runners_2r_indef` | exclude_open_runners | $191517 | $-59401 | 3.22 | 22 | 65 |
