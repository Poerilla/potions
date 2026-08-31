# Structure-program ST — broker-like replay

Plan **touch_st_align** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **touch** · signals: **internal**

| market   | instrument   | plan           |   risk_pts |   risk_price | slug                 |   sessions |   trades |   units |      net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:---------------|-----------:|-------------:|:---------------------|-----------:|---------:|--------:|-------------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | touch_st_align |          8 |            8 | nq_touch_st_align_r8 |       2011 |     1391 |   20865 | -1.24668e+06 |    -1.38325e+06 |             -1.39987e+06 |             -0.89 |          31.46 |           0.843 |
