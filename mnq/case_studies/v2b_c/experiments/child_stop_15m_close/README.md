# v2b_c Child Stop 15m Close-Inside Experiment

This experiment keeps tier-1 v2b OCO entry, targets, wide parent stops, and child limit rules unchanged.

Only the child partial-stop rule changes:

- Base v2b_c: child contracts are stopped on an intrabar touch of the near OR boundary: RH for long children, RL for short children.
- This variant: child contracts are stopped only after a completed 15-minute candle closes back inside that boundary.
- Long child exit trigger: 15-minute close `<= RH`; child exits at that close.
- Short child exit trigger: 15-minute close `>= RL`; child exits at that close.
- Parent/tier-1 contract still uses the original wide v2b stop: RL for longs, RH for shorts.

| Variant | Legs | Net | Max DD | Win rate | PF | Child add rate | Avg contracts | Child partial exits | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| base v2b_c / v2b_child edge child stop | 1992 | $22,608.00 | $-6,742.00 | 48.39% | 1.12 | 57.83% | 1.94 | n/a | `/home/tester/hsm/potions/mnq/case_studies/v2b_child/mnq_orb_open_limit_v2b_child_3max.csv` |
| 15m close-inside child stop | 1992 | $19,824.00 | $-7,399.50 | 47.29% | 1.09 | 57.83% | 1.99 | 829 | `/home/tester/hsm/potions/mnq/case_studies/v2b_c/experiments/child_stop_15m_close/mnq_orb_open_limit_v2b_child_3max_15m_close_child_stop.csv` |
