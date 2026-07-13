# YM shuffled_stpmc_side Random Delayed-Gate Replay

True `Engine + PaperBroker + StrategyPlugin` random delayed-arming replay. Strategy rules and broker realism are unchanged; only `dynamic_sizing_events` is randomized.

| Seeds | Real gate events | Median net | P5 net | P95 net | Median fills | Real net | Real fills | Real net percentile | p(null >= real) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 | 375 | $99297.50 | $53209.31 | $153268.31 | 176.0 | $320190.00 | 347 | 100.0 | 0.0050 |

Allocator-grade note: this report has 200+ random seeds; the p-value is suitable as a first null estimate.

![Net distribution](net_distribution.png)

Files:

- `summary_by_seed.csv`
- `null_distribution.csv`
- generated events under `../../generated_events/ym/shuffled_stpmc_side/`
