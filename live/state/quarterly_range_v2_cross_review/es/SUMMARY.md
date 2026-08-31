# ES v2 short + accumulate review

Hub: `/home/tester/hsm/potions/live/state/quarterly_range_v2_cross_review/es`
Broker fills: `/home/tester/hsm/potions/live/state/es_quarterly_range_breakout_broker/states/es_quarterly_range_breakout/fills.csv`

## Broker book: 60 trades · net **$1,249,968**

| side | n | net | WR |
|---|---:|---:|---:|
| long | 47 | $1,169,964 | 79% |
| short | 13 | $80,003 | 46% |

## Short issues (NQ-style)

- Shorts: n=13 · net **$80,003** · WR 46%
- Median MFE 0.5835010060362174W · before mid 0.5835010060362174W
- Reach 0.2/0.4/0.6/0.8W: 0.8461538461538461 / 0.6153846153846154 / 0.46153846153846156 / 0.3076923076923077
- Stop-only shorts: 2 · $-175,448
- Skip shorts (longs only): **$1,169,964** (Δ $-80,003)
- Early-fail <0.2W by d3: $1,374,235 (Δ $124,268)
- Adheres to NQ short pattern (shorts ~noise / weak WR): **True**

## Accumulate (the two)

Pandas all-in 8: **$1,249,752**

- **2w_1perd_cap10**: $736,870 · avg qty 6.2 · vs all-in $-512,882 · no-fill 0 · better/worse 23/37
- **1w_2contracts_per_week**: $237,697 · avg qty 1.8 · vs all-in $-1,012,056 · no-fill 7 · better/worse 19/41

## Stance

- Accumulate still lags all-in (best 2w_1perd_cap10 $736,870 vs all-in $1,249,752).
- Shorts contribute material net — NQ-style skip is not free here.
