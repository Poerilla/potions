# MNQ Monthly ORB 4H Close-Entry Review

This sidecar study keeps the first-3-session monthly opening range, max two attempts per month, opposite-boundary stop, measured-move target, and restricted close-back-inside behavior. The changed assumption is entry: instead of filling at the opening-range boundary after a daily breakout, the new variants wait for a 4-hour candle to close outside the range and enter at that 4-hour close.

For this revised 4-hour variant, close-back-inside is evaluated only on the daily close. Entries that already close beyond the measured-move target are skipped as stale/overextended. The engine allows only one open trade at a time and up to two completed attempts per month.

| Variant | Trades | Net pts | Net USD | Max closed DD | Win rate | PF | Avg MAE pts | Max MAE pts | Range-close exits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily restricted boundary entry | 141 | 22,019.5 | $44,039 | $-2,394 | 50.4% | 3.58 | 115.8 | 796.8 | 66 |
| 4h restricted close entry | 162 | 3,617.8 | $7,236 | $-6,656 | 44.4% | 1.25 | 159.7 | 966.5 | 85 |
| Daily restricted scaleout3 boundary entry | 139 | 52,577.0 | $105,154 | $-3,411 | 67.6% | 4.73 | 137.0 | 1039.2 | 66 |
| 4h restricted scaleout3 close entry | 151 | 6,044.7 | $12,089 | $-11,732 | 43.0% | 1.18 | 181.3 | 829.0 | 89 |

## Outputs

- `mnq/mnq_monthly_orb_restricted_4h_close_entry.csv`
- `mnq/mnq_monthly_orb_restricted_scaleout3_4h_close_entry.csv`
- `mnq/case_studies/monthly_orb/baseline_restricted_4h_close_entry/`
- `mnq/case_studies/monthly_orb/baseline_restricted_scaleout3_4h_close_entry/`

## Causality Note

The 4-hour breakout close is knowable only after the candle closes. A live implementation would place the order immediately after that close; actual fill may be a tick or more away from the plotted close. This is much less optimistic than the old boundary retest assumption, but a stricter next-4-hour-open/market-fill stress pass is still useful before live testing.
