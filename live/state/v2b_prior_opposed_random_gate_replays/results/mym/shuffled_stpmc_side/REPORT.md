# MYM shuffled_stpmc_side Random Delayed-Gate Replay

True `Engine + PaperBroker + StrategyPlugin` random delayed-arming replay. Strategy rules and broker realism are unchanged; only `dynamic_sizing_events` is randomized.

| Seeds | Real gate events | Median net | P5 net | P95 net | Median fills | Real net | Real fills | Real net percentile | p(null >= real) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 | 368 | $8524.56 | $2657.61 | $13492.94 | 173.0 | $26053.62 | 333 | 100.0 | 0.0050 |

Allocator-grade note: this report has 200+ random seeds; the p-value is suitable as a first null estimate.

![Net distribution](net_distribution.png)

Files:

- `summary_by_seed.csv`
- `null_distribution.csv`
- generated events under `../../generated_events/mym/shuffled_stpmc_side/`
