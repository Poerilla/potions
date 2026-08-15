# OANDA curated fault replay

Generated: 2026-08-15T17:57:23Z
Mode: `live` (containment enforce)
Fixtures: `live/tests/fixtures/oanda_faults/cases/`
Harness: `python -m potions.live.demo.oanda_fault_replay`

## Results (9/9 pass)

| Case | Book | Class | Action | Supervisor | Bars | Plugin | Live fills |
|------|------|-------|--------|------------|------|--------|------------|
| 2026-08-13_foreign_bleed_synthetic | focus_eurusd | foreign_bleed | detect:foreign_bleed,flattened:EURUSD,supervisor_flat_for_day | flat_for_day | 0 | - | - |
| 2026-08-13_stop_only_v2b | nas100 | stop_only | detect:stop_only,freeze_entries | entry_frozen | 1537 | ok | 0 non-eod / 1 total |
| 2026-08-13_stop_only_v2b | spx500 | stop_only | detect:stop_only,freeze_entries | entry_frozen | 1514 | ok | 0 non-eod / 1 total |
| 2026-08-13_us30_3r_open_no_bracket | us30 | open_without_brackets | detect:open_without_brackets,freeze_entries | entry_frozen | 0 | - | - |
| 2026-08-14_orphan_stop_flat_v2b | nas100 | orphan_protective | detect:orphan_protective,cancel_orphan_protectives:1 | running | 1286 | ok | 0 non-eod / 0 total |
| 2026-08-14_orphan_stop_flat_v2b | spx500 | orphan_protective | detect:orphan_protective,cancel_orphan_protectives:1 | running | 1624 | ok | 0 non-eod / 0 total |
| 2026-08-14_stream_hung_missed_entry | nas100 | stream_stale | detect:stream_stale,freeze_entries | entry_frozen | 1286 | ok | 0 non-eod / 0 total |
| healthy_protected_v2b | nas100 | ok | - | running | 0 | - | - |
| qty_mismatch_hard | nas100 | qty_mismatch | detect:qty_mismatch,flattened:NAS100,supervisor_flat_for_day | flat_for_day | 0 | - | - |

## Purpose

Offline regression of real Aug 13–14 OANDA practice incidents
(stop-only, orphan protective, stream-hung missed entry, open-without-brackets,
foreign bleed, qty mismatch) against daemon containment hardenings.

Default live daemons stay on `POTIONS_OANDA_CONTAINMENT=shadow` until
≥1 week of clean practice shadow.
