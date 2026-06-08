# Inside Restricted Boundary-Close Scaleout TP1 Wide-Stop Study

This is a restricted-only branch of the causal monthly ORB inside-candle-open study.

Rules in this study:

- Entry remains the causal inside opposite candle/run open limit after a valid monthly OR breakout close.
- Pending limits are cancelled if TP1 trades before the limit fills; the strategy then waits for a new setup.
- Initial stop is one monthly range beyond the selected source stop: long = source stop - range; short = source stop + range.
- TP1 is the first monthly measured move: long = range high + range; short = range low - range.
- If a daily close crosses back through the breakout boundary, two contracts are closed at that daily close.
- The final contract remains open for TP1, the wide initial stop, or period close.

Boundary close means close <= monthly OR high for longs, and close >= monthly OR low for shorts. Intraday stop/target events are processed before the daily close scaleout.

| Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | TP1 trades | Direct TP1 | Boundary close -> TP1 | Boundary close -> stop | Boundary close -> period | Boundary close trades | Full stops | Period closes |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 53 | 385 | $13,128.50 | $-5,743.00 | $4,376.17 | $-1,914.33 | 54.72% | 1.45 | 123.85 | 0.07 | 22 | 6 | 16 | 12 | 18 | 46 | 1 | 0 |

## Outputs

- Trades CSV: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_boundary_close_scaleout_tp1_wide_stop_intraday.csv`
- Cancelled stale limits CSV: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_boundary_close_scaleout_tp1_wide_stop_cancelled_limits_intraday.csv`
