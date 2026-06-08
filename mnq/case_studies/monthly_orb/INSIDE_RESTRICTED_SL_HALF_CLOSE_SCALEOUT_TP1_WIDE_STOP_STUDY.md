# Inside Restricted SL-Half-Close Scaleout TP1 Wide-Stop Study

This branch tests a deeper restriction trigger than boundary close.

Rules in this study:

- Entry remains the causal inside opposite candle/run open limit after a valid monthly OR breakout close.
- Pending limits are cancelled if TP1 trades before the limit fills; the strategy then waits for a new setup.
- Initial stop is one monthly range beyond the selected source stop: long = source stop - range; short = source stop + range.
- The half-stop scaleout level is halfway between entry and the wide initial stop.
- Two contracts are closed only when the daily close is strictly more than halfway to the stop: long close < halfway level; short close > halfway level.
- The final contract remains open for TP1, the wide initial stop, or period close.

Intraday stop/target events are processed before the daily close scaleout.

| Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | TP1 trades | Direct TP1 | SL-half close -> TP1 | SL-half close -> stop | SL-half close -> period | SL-half close trades | Full stops | Period closes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 53 | 385 | $13,099.50 | $-13,423.50 | $4,366.50 | $-4,474.50 | 47.17% | 1.20 | 123.58 | 0.10 | 22 | 21 | 1 | 11 | 6 | 18 | 2 | 12 |

## Outputs

- Trades CSV: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_sl_half_close_scaleout_tp1_wide_stop_intraday.csv`
- Cancelled stale limits CSV: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_sl_half_close_scaleout_tp1_wide_stop_cancelled_limits_intraday.csv`
