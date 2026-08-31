# Structure-program ST — broker-like replay

Plan **scale_run** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **resting** · signals: **structure_only**

| market   | instrument   | plan      |   risk_pts |   risk_price | slug                           |   sessions |   trades |   units |      net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:----------|-----------:|-------------:|:-------------------------------|-----------:|---------:|--------:|-------------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | scale_run |          8 |            8 | nq_scale_run_r8_struct_resting |       2011 |      493 |    7395 | -2.12618e+06 |    -2.18398e+06 |             -2.19345e+06 |             -0.97 |           6.63 |           0.185 |
