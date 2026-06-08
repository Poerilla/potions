# MNQ Monthly ORB 4H Swing-Stop Review

This sidecar study keeps the first-3-session monthly opening range, max two attempts per month, and measured-move target. The changed assumptions are entry and stop: instead of filling at the opening-range boundary after a daily breakout, the new variants wait for a 4-hour candle to close outside the range and enter at that 4-hour close; instead of using a range-close restriction, they stop at the most recent confirmed 4-hour swing.

For longs, the stop is the most recent confirmed 4-hour swing low. For shorts, it is the most recent confirmed 4-hour swing high. A swing is only usable after the next 4-hour candle confirms it. If the swing is beyond the opposing opening-range boundary, the stop is pulled to the OR midpoint. There is no close-back-inside exit; trades exit by stop, target, or period close. The engine allows only one open trade at a time and up to two completed attempts per month. After a completed trade, the next attempt must re-arm with a daily close back inside the monthly OR, then a fresh 4-hour close outside.

| Variant | Trades | Net pts | Net USD | Max closed DD | Win rate | PF | Avg MAE pts | Max MAE pts | Range-close exits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Daily restricted boundary entry | 141 | 22,019.5 | $44,039 | $-2,394 | 50.4% | 3.58 | 115.8 | 796.8 | 66 |
| 4h swing-stop close entry | 131 | 3,939.4 | $7,879 | $-8,336 | 46.6% | 1.21 | 228.4 | 1831.8 | 0 |
| Daily restricted scaleout3 boundary entry | 139 | 52,577.0 | $105,154 | $-3,411 | 67.6% | 4.73 | 137.0 | 1039.2 | 66 |
| 4h swing-stop scaleout3 close entry | 131 | 8,445.6 | $16,891 | $-15,093 | 46.6% | 1.21 | 241.4 | 1831.8 | 0 |

## Outputs

- `mnq/mnq_monthly_orb_4h_swing_stop.csv`
- `mnq/mnq_monthly_orb_scaleout3_4h_swing_stop.csv`
- `mnq/data/mnq_front_month_4h_from_1m.csv`
- `mnq/case_studies/monthly_orb/baseline_4h_swing_stop/`
- `mnq/case_studies/monthly_orb/baseline_scaleout3_4h_swing_stop/`

## Causality Note

The 4-hour breakout close and the most recent confirmed swing are knowable only after the candle closes. A live implementation would place the order immediately after that close; actual fill may be a tick or more away from the plotted close. A stricter next-4-hour-open/market-fill stress pass is still useful before live testing.

## Regeneration

Normal rerun, using the cached 4-hour front-month bars:

```bash
python3 potions/scripts/monthly_orb_4h_close_entry.py
```

Rebuild the 4-hour cache from the 1-minute DBN only when raw data changes:

```bash
python3 potions/scripts/monthly_orb_4h_close_entry.py --rebuild-4h-cache
```
