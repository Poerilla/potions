# Inside Source-Stop 3-Contract Range-Target Ladder Intraday Study

Corrected interpretation of `1R/2R/3R`: targets are monthly opening-range multiples from the breakout boundary, not source-stop risk multiples.

- Long target 1 = monthly OR high + range; target 2 = OR high + 2x range; target 3 = OR high + 3x range.
- Short target 1 = monthly OR low - range; target 2 = OR low - 2x range; target 3 = OR low - 3x range.
- Initial stop remains the selected inside-candle/run low for longs and high for shorts.
- After target 1, remaining units move their protective stop to the breakout-side range boundary.
- Restricted still exits at daily close if price closes back inside the monthly OR.

Results are MNQ gross before fees/slippage, using raw 1-minute bars for fill and exit order.

| Variant | Trades | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | Target 1 | Target 2 | Target 3 | Full stops | Boundary stops | Range closes | Period closes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unrestricted ladder range-target 1/2/3 | 69 | $3,685.00 | $-11,923.50 | $1,228.33 | $-3,974.50 | 26.09% | 1.08 | 26.70 | -0.04 | 14 | 6 | 1 | 47 | 4 | 0 | 17 |
| restricted ladder range-target 1/2/3 | 76 | $13,793.50 | $-9,355.00 | $4,597.83 | $-3,118.33 | 47.37% | 1.74 | 90.75 | 0.02 | 6 | 3 | 0 | 23 | 2 | 46 | 5 |

## Read

This version tests the idea you meant: the first scale-out waits for the full monthly measured move. It should be judged against the earlier risk-multiple ladder separately, because the target distances are much larger.

## Output CSVs

- unrestricted ladder range-target 1/2/3: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_source_stop_ladder3_range_targets_intraday.csv`
- restricted ladder range-target 1/2/3: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_source_stop_ladder3_range_targets_intraday.csv`
