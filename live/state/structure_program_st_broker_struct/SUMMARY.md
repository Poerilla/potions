# Structure-program ST — broker-like replay

Plan **scale_run** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **resting** · signals: **structure_only**

| market   | instrument   | plan      |   risk_pts |   risk_price | slug                           |   sessions |   trades |   units |    net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:----------|-----------:|-------------:|:-------------------------------|-----------:|---------:|--------:|-----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | scale_run |          8 |            8 | nq_scale_run_r8_struct_resting |       2011 |    43474 |  651990 | -1.809e+09 |      -1.809e+09 |             -1.90993e+08 |             -9.47 |           0.63 |           0.002 |
