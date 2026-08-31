# GBPUSD prior width vs losses

GBPUSD quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/gbpusd/prior_width_study`

What is large? Trade-sample p50=0.07732, p75=0.1124, p90=0.1409.
Q4_large ~= W in [0.1124, 0.3522] (26 trades, WR 58%, net $133051).

Skip Q4 counterfactual: keep $163328 (delta $-133051 vs baseline $296379).

Spearman width↔net: rho=-0.03

## By width quartile

 width_q    n  win_rate      net      avg_net     avg_R  stop_rate  loss_n  loss_usd   w_min   w_max    w_med  loss_share
Q1_small 26.0  0.538462  -3586.2  -137.930769 -0.017357   0.269231    12.0 -236621.4 0.03753 0.06824 0.056115    0.223343
      Q2 25.0  0.760000 222160.0  8886.400000  0.308486   0.080000     6.0 -145440.0 0.06831 0.07656 0.073230    0.137278
      Q3 25.0  0.480000 -55245.6 -2209.824000 -0.045704   0.320000    13.0 -334337.2 0.07809 0.11229 0.091520    0.315575
Q4_large 26.0  0.576923 133051.0  5117.346154  0.106309   0.076923    11.0 -343054.6 0.11245 0.35220 0.137210    0.323803
