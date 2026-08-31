# Structure-program ST — broker-like replay

Plan **scale_run** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **touch** · signals: **external**

| market   | instrument   | plan      |   risk_pts |   risk_price | slug                |   sessions |   trades |   units |   net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:----------|-----------:|-------------:|:--------------------|-----------:|---------:|--------:|----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | scale_run |          8 |            8 | nq_scale_run_r8_ext |       2011 |      111 |    1665 |   -217179 |         -224085 |                  -228021 |             -0.95 |            2.7 |           0.174 |
