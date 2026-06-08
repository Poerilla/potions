# Monthly ORB Restricted Stop-Limit Cycle: 4H Causal Sim

This sidecar keeps the long-only restricted stop/limit cycle rules, but uses 4-hour bars derived from front-month 1-minute data. Orders armed by a close or TP1 event become live on the next 4-hour bar.

Two daily-close exit treatments are compared:

- `close`: fills daily-close exits at the confirming 4-hour close. This is closer to research parity.
- `next_open`: fills daily-close exits at the next 4-hour bar open. This is closer to live automation.

Fresh fills do not receive same-bar target credit. Same-bar false-breakout daily-close invalidations are honored.

## Summary

| Market | Exit Fill | Packages | Net Pts | Net USD | Max DD USD | Win Rate | PF | Avg MAE | Max MAE | False BO | Top Refills | Bottom Limits | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MNQ | close | 141 | 27,390.0 | $54,780 | $-10,330 | 51.1% | 1.69 | 210.1 | 1,039.2 | 0 | 28 | 20 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv) |
| MNQ | next_open | 143 | 26,318.6 | $52,637 | $-14,906 | 50.3% | 1.61 | 212.5 | 1,039.2 | 0 | 28 | 27 | [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv) |
| NQ | close | 338 | 32,482.1 | $649,642 | $-103,068 | 45.0% | 1.63 | 112.4 | 1,038.0 | 0 | 56 | 55 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv) |
| NQ | next_open | 342 | 30,690.9 | $613,818 | $-148,712 | 44.7% | 1.55 | 115.6 | 1,038.0 | 0 | 56 | 66 | [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv) |

## Notes

- The sim still cannot know the exact intrabar path inside a 4-hour candle.
- `next_open` is the more realistic daily-close exit mode for automation because the daily close is only known after the bar closes.
- If a 4-hour bar touches both the breakout stop and bottom limit while both are logically available, the default priority is `breakout`, matching the latest daily research state machine.
- This is not yet a Pine/MultiCharts implementation; it is the causal Python reference pass before porting.

## Outputs

- [Hardened variant comparison](HARDENED_VARIANTS.md)
- [MNQ close 4h charts](charts_mnq_close/INDEX.md)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.events.csv)
- [MNQ next_open 4h charts](charts_mnq_next_open/INDEX.md)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv)
- [mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.events.csv](mnq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.events.csv)
- [NQ close 4h charts](charts_nq_close/INDEX.md)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_close.events.csv)
- [NQ next_open 4h charts](charts_nq_next_open/INDEX.md)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.csv)
- [nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.events.csv](nq_monthly_orb_restricted_stop_limit_cycle_4h_causal_next_open.events.csv)
