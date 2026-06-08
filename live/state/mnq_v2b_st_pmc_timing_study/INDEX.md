# MNQ v2b / ST+PMC Causal Timing Study

This report asks two separate causal questions:

1. **v2b second:** when MNQ hourly ST+PMC has already fired earlier in the session, how does a later same-direction MNQ v2b trade behave versus base v2b?
2. **ST+PMC second:** when MNQ v2b has already fired earlier in the session, how does a later same-direction MNQ hourly ST+PMC trade behave versus base ST+PMC?

Definitions:

- `prior_aligned`: the other strategy already had a same-session entry in the same direction before the subject trade entry.
- `prior_opposed`: the other strategy already had a same-session entry, but only in the opposite direction before the subject trade entry.
- `no_prior_signal`: no earlier same-session entry from the other strategy.
- Same-timestamp entries are not treated as prior information.

## v2b As The Second Signal

| bucket | trades | wins | losses | win_rate_pct | net_usd | avg_usd | profit_factor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2b_base_all | 1384 | 742 | 642 | 53.61 | 74441.50 | 53.79 | 1.160 |
| v2b_prior_aligned | 132 | 70 | 62 | 53.03 | 3774.50 | 28.59 | 1.077 |
| v2b_prior_opposed | 183 | 121 | 62 | 66.12 | 57668.50 | 315.13 | 2.237 |
| v2b_no_prior_signal | 1069 | 551 | 518 | 51.54 | 12998.50 | 12.16 | 1.035 |

## ST+PMC As The Second Signal

| bucket | trades | wins | losses | win_rate_pct | net_usd | avg_usd | profit_factor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| st_pmc_base_all | 805 | 255 | 550 | 31.68 | 8706.56 | 10.82 | 1.299 |
| st_pmc_prior_aligned | 196 | 68 | 128 | 34.69 | 3442.00 | 17.56 | 1.517 |
| st_pmc_prior_opposed | 141 | 39 | 102 | 27.66 | 480.86 | 3.41 | 1.091 |
| st_pmc_no_prior_signal | 468 | 148 | 320 | 31.62 | 4783.70 | 10.22 | 1.278 |

## Read

- **v2b after same-direction ST+PMC is not better than base v2b** in this pass: win rate changes by -0.58 pct points, PF drops from 1.160 to 1.077, and average trade drops from $53.79 to $28.59.
- **v2b after opposite-direction ST+PMC is the strongest v2b timing bucket**: win rate changes by +12.51 pct points, PF improves to 2.237, and average trade rises to $315.13. This looks more like a failed hourly ST+PMC / intraday reversal gate than an alignment gate.
- **ST+PMC after same-direction v2b improves modestly versus base ST+PMC**: win rate changes by +3.01 pct points, PF improves from 1.299 to 1.517, and average trade rises from $10.82 to $17.56.
- **ST+PMC after opposite-direction v2b is weaker**: win rate changes by -4.02 pct points and PF drops to 1.091.

Practical first model idea: use **v2b as a potential confirmation gate for later ST+PMC**, but do not use same-direction ST+PMC as a v2b size-up gate yet. For v2b, the stronger research branch is the opposite-direction prior ST+PMC bucket, which needs chart review before treating it as a live sizing signal.

## Files

- `v2b_timing_summary.csv`
- `st_pmc_timing_summary.csv`
- `v2b_trade_timing.csv`
- `st_pmc_trade_timing.csv`
