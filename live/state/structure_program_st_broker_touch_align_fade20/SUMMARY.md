# Structure-program ST — broker-like replay

Plan **touch_st_align_fade20** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **touch** · signals: **internal**

| market   | instrument   | plan                  |   risk_pts |   risk_price | slug                        |   sessions |   trades |   units |   net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:----------------------|-----------:|-------------:|:----------------------------|-----------:|---------:|--------:|----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | touch_st_align_fade20 |          8 |            8 | nq_touch_st_align_fade20_r8 |       2011 |      922 |   13830 |   -870732 |         -873252 |                  -882962 |             -0.99 |          19.49 |           0.749 |
