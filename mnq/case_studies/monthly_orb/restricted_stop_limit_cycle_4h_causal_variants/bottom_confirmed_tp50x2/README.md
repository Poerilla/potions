# Monthly ORB Restricted Stop-Limit Cycle: 4H Causal Sim

This sidecar keeps the long-only restricted stop/limit cycle rules, but uses 4-hour bars derived from front-month 1-minute data. Orders armed by a close or TP1 event become live on the next 4-hour bar.

Two daily-close exit treatments are compared:

- `close`: fills daily-close exits at the confirming 4-hour close. This is closer to research parity.
- `next_open`: fills daily-close exits at the next 4-hour bar open. This is closer to live automation.

Fresh fills do not receive same-bar target credit. Same-bar false-breakout daily-close invalidations are honored.

## Summary

| Market | Exit Fill | Packages | Net Pts | Net USD | Max DD USD | Win Rate | PF | Avg MAE | Max MAE | False BO | Top Refills | Bottom Limits | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MNQ | close | 139 | 32,647.1 | $65,294 | $-13,447 | 56.1% | 1.73 | 209.3 | 1,039.2 | 0 | 28 | 18 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv) |
| MNQ | next_open | 141 | 31,194.9 | $62,390 | $-15,703 | 55.3% | 1.65 | 211.8 | 1,039.2 | 0 | 28 | 25 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv) |
| NQ | close | 335 | 37,992.5 | $759,850 | $-127,200 | 49.6% | 1.64 | 112.1 | 1,038.0 | 0 | 56 | 49 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv) |
| NQ | next_open | 338 | 36,554.8 | $731,095 | $-156,622 | 48.8% | 1.58 | 115.2 | 1,038.0 | 0 | 56 | 61 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv) |

## Notes

- The sim still cannot know the exact intrabar path inside a 4-hour candle.
- `next_open` is the more realistic daily-close exit mode for automation because the daily close is only known after the bar closes.
- If a 4-hour bar touches both the breakout stop and bottom limit while both are logically available, the default priority is `breakout`, matching the latest daily research state machine.
- This is not yet a Pine/MultiCharts implementation; it is the causal Python reference pass before porting.

## Outputs

- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.events.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.events.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed_tp50x2.events.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed_tp50x2.events.csv)
