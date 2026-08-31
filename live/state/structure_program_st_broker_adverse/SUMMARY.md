# Structure-program ST — broker-like replay

Plan **split15** risk=12 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **adverse** (min_bars=0)

| market   | instrument   | plan    |   risk_pts |   risk_price | slug           |   sessions |   trades |   units |   net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:--------|-----------:|-------------:|:---------------|-----------:|---------:|--------:|----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | split15 |         12 |           12 | nq_split15_r12 |       2011 |      255 |    3820 |   -203780 |         -209130 |                  -199035 |             -1.02 |          11.91 |            0.56 |
