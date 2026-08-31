# Structure-program ST — broker-like replay

Plan **scale_run** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **sweep_reclaim** · signals: **external**

| market   | instrument   | plan      |   risk_pts |   risk_price | slug                              |   sessions |   trades |   units |   net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:----------|-----------:|-------------:|:----------------------------------|-----------:|---------:|--------:|----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | scale_run |          8 |            8 | nq_scale_run_r8_ext_sweep_reclaim |       2011 |      286 |    4290 |   -441329 |         -476464 |                  -496504 |             -0.89 |           7.81 |           0.419 |
