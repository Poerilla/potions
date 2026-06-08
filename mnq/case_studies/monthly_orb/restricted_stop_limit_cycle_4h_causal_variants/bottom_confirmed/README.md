# Monthly ORB Restricted Stop-Limit Cycle: 4H Causal Sim

This sidecar keeps the long-only restricted stop/limit cycle rules, but uses 4-hour bars derived from front-month 1-minute data. Orders armed by a close or TP1 event become live on the next 4-hour bar.

Two daily-close exit treatments are compared:

- `close`: fills daily-close exits at the confirming 4-hour close. This is closer to research parity.
- `next_open`: fills daily-close exits at the next 4-hour bar open. This is closer to live automation.

Fresh fills do not receive same-bar target credit. Same-bar false-breakout daily-close invalidations are honored.

## Summary

| Market | Exit Fill | Packages | Net Pts | Net USD | Max DD USD | Win Rate | PF | Avg MAE | Max MAE | False BO | Top Refills | Bottom Limits | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MNQ | close | 139 | 28,590.0 | $57,180 | $-10,330 | 51.8% | 1.74 | 209.3 | 1,039.2 | 0 | 28 | 18 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv) |
| MNQ | next_open | 141 | 27,517.1 | $55,034 | $-14,906 | 51.1% | 1.66 | 211.8 | 1,039.2 | 0 | 28 | 25 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv) |
| NQ | close | 335 | 33,121.0 | $662,420 | $-103,068 | 45.4% | 1.65 | 112.1 | 1,038.0 | 0 | 56 | 49 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv) |
| NQ | next_open | 338 | 32,090.1 | $641,802 | $-148,712 | 45.3% | 1.59 | 115.2 | 1,038.0 | 0 | 56 | 61 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv) |

## Notes

- The sim still cannot know the exact intrabar path inside a 4-hour candle.
- `next_open` is the more realistic daily-close exit mode for automation because the daily close is only known after the bar closes.
- If a 4-hour bar touches both the breakout stop and bottom limit while both are logically available, the default priority is `breakout`, matching the latest daily research state machine.
- This is not yet a Pine/MultiCharts implementation; it is the causal Python reference pass before porting.

## Outputs

- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.events.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.events.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close_bottom_confirmed.events.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open_bottom_confirmed.events.csv)
