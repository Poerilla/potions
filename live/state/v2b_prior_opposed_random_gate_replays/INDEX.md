# v2b Prior-Opposed Random Delayed-Gate Replays

True StrategyPlugin null tests for the prior-opposed delayed-arming gate. These are not completed-trade resamples.

Current status: **200-seed shuffled-label** (`shuffled_stpmc_side`) complete on NQ, MNQ, YM, MYM (all p = 0.0050). **200-seed stratified** (`stratified_fine_buckets`) complete on same four markets. See scale queue in [`../../data/docs/AUDIT_TRACKER.md`](../../data/docs/AUDIT_TRACKER.md).

## Summary

| Market | Method | Seeds | Median Net | Best Net | Worst Net | Median Fills | Report |
|---|---|---:|---:|---:|---:|---:|---|
| MNQ | `shuffled_stpmc_side` | 200 | $38638.25 | $57201.00 | $15320.50 | 173.5 | [REPORT](results/mnq/shuffled_stpmc_side/REPORT.md) |
| MNQ | `stratified_event_count` | 200 | $-231.25 | $31681.50 | $-18348.50 | 172.0 | [REPORT](results/mnq/stratified_event_count/REPORT.md) |
| MYM | `shuffled_stpmc_side` | 200 | $8524.56 | $16636.12 | $-583.00 | 173.0 | [REPORT](results/mym/shuffled_stpmc_side/REPORT.md) |
| MYM | `stratified_event_count` | 200 | $-5878.19 | $3180.25 | $-18666.62 | 188.0 | [REPORT](results/mym/stratified_event_count/REPORT.md) |
| NQ | `shuffled_stpmc_side` | 200 | $370025.00 | $568650.00 | $94127.50 | 173.0 | [REPORT](results/nq/shuffled_stpmc_side/REPORT.md) |
| NQ | `stratified_event_count` | 200 | $11756.25 | $308293.75 | $-290763.75 | 171.0 | [REPORT](results/nq/stratified_event_count/REPORT.md) |
| NQ | `unconstrained_event_count` | 1 | $28946.25 | $28946.25 | $28946.25 | 137.0 | [REPORT](results/nq/unconstrained_event_count/REPORT.md) |
| YM | `shuffled_stpmc_side` | 200 | $99297.50 | $189303.75 | $-26130.00 | 176.0 | [REPORT](results/ym/shuffled_stpmc_side/REPORT.md) |
| YM | `stratified_event_count` | 200 | $-42777.50 | $95548.75 | $-163755.00 | 191.0 | [REPORT](results/ym/stratified_event_count/REPORT.md) |

## Reports

- [MNQ / shuffled_stpmc_side](results/mnq/shuffled_stpmc_side/REPORT.md)
- [MNQ / stratified_event_count](results/mnq/stratified_event_count/REPORT.md)
- [MYM / shuffled_stpmc_side](results/mym/shuffled_stpmc_side/REPORT.md)
- [MYM / stratified_event_count](results/mym/stratified_event_count/REPORT.md)
- [NQ / shuffled_stpmc_side](results/nq/shuffled_stpmc_side/REPORT.md)
- [NQ / stratified_event_count](results/nq/stratified_event_count/REPORT.md)
- [NQ / unconstrained_event_count](results/nq/unconstrained_event_count/REPORT.md)
- [YM / shuffled_stpmc_side](results/ym/shuffled_stpmc_side/REPORT.md)
- [YM / stratified_event_count](results/ym/stratified_event_count/REPORT.md)
