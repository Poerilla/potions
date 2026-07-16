# NQ Resting-Limit Day Timelines

All **1164** regime days for the hour-complete baseline.

## Files

- [`day_event_timeline.csv`](day_event_timeline.csv) — one row per event (7,039 rows)
- [`day_summary.csv`](day_summary.csv) — one row per regime day

## Coverage

| Bucket | Days |
|---|---:|
| Regime days | 1164 |
| ST+PMC same session | 506 |
| No ST+PMC | 658 |
| v2b armed | 500 |
| ST but not armed | 6 |
| v2b filled campaign(s) | 419 |

## Event flow on a traded day

1. `st_pmc_hour_label` → `st_pmc_available_hour_complete`
2. `v2b_or_finalized_and_entry_armed`
3. `v2b_entry_filled` + exit orders placed (`wide_stop` / `tp1` / `tp2` / later `runner_stop`)
4. Partial/exit fills
5. `v2b_eod_flatten` if runner still open
6. `v2b_campaign_closed`

Days with no ST: `st_pmc_none` + `v2b_not_armed`.

Source: `../states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
