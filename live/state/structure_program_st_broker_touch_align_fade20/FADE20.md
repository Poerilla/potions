# touch_st_align_fade20

## Rule add-on
If still through the structure for **20 consecutive 1m bars**, stop waiting for
continuation ST flip and **fade the structure key**:
- limit @ key, opposite side
- stop = key ± 25 (same risk size as first TP rung)
- ladder unchanged: 5@+25→±12, 5@+50, 5@+200, fav ST→BE

Else: original touch→through→ST-align market continuation.

## Results

| | Analytic | PaperBroker |
|--|--:|--:|
| Trades | 670 | 922 |
| Net | +$670k | **−$871k** |
| PF | 1.34 | **0.75** |

vs prior touch_align broker **−$1.25M / PF 0.84** — fade20 loses less but still FAIL
(TRL-2026-00085).

## Structural invalidity (prior touch_align broker book)

See `../structure_program_st_broker_touch_align/invalid_audit/SUMMARY.md`.
Day-key coverage: **~37%** of fills are still/deep through the structure at entry
(through net **−$651k** of the −$1.25M book).
