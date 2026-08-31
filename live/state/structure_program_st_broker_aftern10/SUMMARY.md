# Structure-program ST — broker-like replay

Plan **split15** risk=12 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ST-flip mode: **after_n** (min_bars=10)

| market   | instrument   | plan    |   risk_pts |   risk_price | slug           |   sessions |   trades |   units |   net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:--------|-----------:|-------------:|:---------------|-----------:|---------:|--------:|----------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | split15 |         12 |           12 | nq_split15_r12 |       2011 |      251 |    3755 |   -232126 |         -239479 |                  -238490 |             -0.97 |          20.37 |           0.593 |
