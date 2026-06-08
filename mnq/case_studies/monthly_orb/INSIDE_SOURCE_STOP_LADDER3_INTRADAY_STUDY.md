# Inside Source-Stop 3-Contract Ladder Intraday Study

Setup is the causal monthly ORB inside-candle-open source-stop entry. This study uses 3 contracts: one exits at 1R, one exits at 2R, and one exits at 3R.

After the 1R exit, the remaining two contracts move their stop to the breakout-side monthly OR boundary: monthly OR high for longs and monthly OR low for shorts. To keep this live-realistic, that boundary stop only becomes a protective stop after price has traded on the profitable side of that boundary; until then the original source stop remains active.

Restricted keeps the daily close-back-inside monthly range exit. Results are MNQ gross before fees/slippage, using raw 1-minute bars for fill and exit order.

| Variant | Trades | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | Target 1R | Target 2R | Target 3R | Full stops | Boundary stops | Range closes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unrestricted ladder 1R/2R/3R | 76 | $24,261.00 | $-12,496.00 | $8,087.00 | $-4,165.33 | 51.32% | 1.68 | 159.61 | 0.16 | 42 | 16 | 5 | 30 | 25 | 0 |
| restricted ladder 1R/2R/3R | 77 | $18,802.50 | $-6,854.50 | $6,267.50 | $-2,284.83 | 55.84% | 2.19 | 122.09 | 0.14 | 24 | 11 | 3 | 17 | 13 | 37 |

## Read

The 3R contract does add gross profit, especially in the unrestricted variant, but the boundary-stop logic does not beat the current restricted 2-contract 2R candidate on drawdown-adjusted quality.

The restricted ladder is still constrained by the close-back-inside rule, so it does not get many 3R completions. The unrestricted ladder gives the third contract more room, but the larger open exposure and delayed boundary-stop validity increase drawdown.

## Output CSVs

- unrestricted ladder 1R/2R/3R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_source_stop_ladder3_intraday.csv`
- restricted ladder 1R/2R/3R: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_restricted_source_stop_ladder3_intraday.csv`
