# YM v2 short + accumulate review

Hub: `/home/tester/hsm/potions/live/state/quarterly_range_v2_cross_review/ym`
Broker fills: `/home/tester/hsm/potions/live/state/ym_quarterly_range_breakout_broker/states/ym_quarterly_range_breakout/fills.csv`

## Broker book: 69 trades · net **$303,058**

| side | n | net | WR |
|---|---:|---:|---:|
| long | 53 | $297,731 | 60% |
| short | 16 | $5,327 | 44% |

## Short issues (NQ-style)

- Shorts: n=16 · net **$5,327** · WR 44%
- Median MFE 0.2666059756840566W · before mid 0.2666059756840566W
- Reach 0.2/0.4/0.6/0.8W: 0.6875 / 0.375 / 0.3125 / 0.3125
- Stop-only shorts: 3 · $-66,592
- Skip shorts (longs only): **$297,731** (Δ $-5,327)
- Early-fail <0.2W by d3: $153,245 (Δ $-149,813)
- Adheres to NQ short pattern (shorts ~noise / weak WR): **True**

## Accumulate (the two)

Pandas all-in 8: **$379,372**

- **2w_1perd_cap10**: $253,929 · avg qty 6.3 · vs all-in $-125,443 · no-fill 0 · better/worse 34/35
- **1w_2contracts_per_week**: $155,613 · avg qty 1.9 · vs all-in $-223,759 · no-fill 4 · better/worse 29/40

## Stance

- Accumulate still lags all-in (best 2w_1perd_cap10 $253,929 vs all-in $379,372).
- Skipping shorts is ~flat or better — shorts not earning keep.
