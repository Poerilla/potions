# MNQ v2 short + accumulate review

Hub: `/home/tester/hsm/potions/live/state/quarterly_range_v2_cross_review/mnq`
Broker fills: `/home/tester/hsm/potions/live/state/mnq_quarterly_range_breakout_broker/states/mnq_quarterly_range_breakout/fills.csv`

## Broker book: 31 trades · net **$120,170**

| side | n | net | WR |
|---|---:|---:|---:|
| long | 24 | $118,497 | 75% |
| short | 7 | $1,673 | 43% |

## Short issues (NQ-style)

- Shorts: n=7 · net **$1,673** · WR 43%
- Median MFE 0.3449031786627695W · before mid 0.3449031786627695W
- Reach 0.2/0.4/0.6/0.8W: 0.5714285714285714 / 0.42857142857142855 / 0.14285714285714285 / 0.0
- Stop-only shorts: 1 · $-15,630
- Skip shorts (longs only): **$118,497** (Δ $-1,673)
- Early-fail <0.2W by d3: $97,417 (Δ $-22,753)
- Adheres to NQ short pattern (shorts ~noise / weak WR): **True**

## Accumulate (the two)

Pandas all-in 8: **$118,883**

- **2w_1perd_cap10**: $121,176 · avg qty 6.2 · vs all-in $2,293 · no-fill 1 · better/worse 17/14
- **1w_2contracts_per_week**: $33,086 · avg qty 1.8 · vs all-in $-85,797 · no-fill 3 · better/worse 11/20

## Stance

- Best accum 2w_1perd_cap10 beats all-in.
- Skipping shorts is ~flat or better — shorts not earning keep.
