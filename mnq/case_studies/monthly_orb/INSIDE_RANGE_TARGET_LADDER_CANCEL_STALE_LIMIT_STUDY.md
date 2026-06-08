# Inside Range-Target Ladder With Stale-Limit Cancellation

Targets are monthly OR range multiples: long target 1 = RH + range, target 2 = RH + 2x range, target 3 = RH + 3x range; shorts use RL - range multiples.

New rules in this study:

- If target 1 trades before the pending inside-candle limit fills, the limit is cancelled and the strategy waits for a new setup.
- Unrestricted uses the opposing monthly OR boundary as the initial stop: range low for longs, range high for shorts.
- Restricted keeps the source inside-candle/run stop and keeps the close-back-inside range exit.

Same-minute pending target/fill ambiguity is resolved target-first, meaning the stale limit is cancelled.

| Variant | Stop mode | Trades | Cancelled stale limits | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Target 1 | Target 2 | Target 3 | Full stops | Boundary stops | Range closes | Period closes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unrestricted range-stop cancel-stale ladder | opposing_range | 58 | 346 | $-816.00 | $-14,890.50 | $-272.00 | $-4,963.50 | 36.21% | 0.99 | -7.03 | 18 | 6 | 1 | 30 | 5 | 0 | 22 |
| restricted source-stop cancel-stale ladder | source | 66 | 374 | $19,069.50 | $-5,902.00 | $6,356.50 | $-1,967.33 | 48.48% | 2.16 | 144.47 | 6 | 3 | 0 | 18 | 1 | 42 | 5 |

## Output CSVs

- unrestricted range-stop cancel-stale ladder trades: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_range_stop_ladder3_range_targets_cancel_stale_intraday.csv`
- unrestricted range-stop cancel-stale ladder cancelled stale limits: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_range_stop_ladder3_range_targets_cancel_stale_cancelled_limits_intraday.csv`
- restricted source-stop cancel-stale ladder trades: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_source_stop_ladder3_range_targets_cancel_stale_intraday.csv`
- restricted source-stop cancel-stale ladder cancelled stale limits: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_source_stop_ladder3_range_targets_cancel_stale_cancelled_limits_intraday.csv`
