# XAGUSD prior width vs losses

XAGUSD quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/xagusd/prior_width_study`

What is large? Trade-sample p50=3.363, p75=5.096, p90=10.13.
Q4_large ~= W in [5.368, 38.46] (27 trades, WR 56%, net $-214650).

Skip Q4 counterfactual: keep $23669 (delta $214650 vs baseline $-190981).

Spearman width↔net: rho=0.09

## By width quartile

 width_q    n  win_rate       net      avg_net     avg_R  stop_rate  loss_n  loss_usd  w_min  w_max  w_med  loss_share
Q1_small 27.0  0.629630    7694.2   284.970370  0.094559   0.185185    10.0  -59900.6  0.697  2.092  1.508    0.056233
      Q2 27.0  0.518519   -6128.4  -226.977778 -0.028722   0.370370    13.0 -129713.6  2.163  3.320  2.907    0.121771
      Q3 27.0  0.555556   22102.8   818.622222  0.004650   0.185185    12.0 -186163.2  3.405  5.005  4.526    0.174763
Q4_large 27.0  0.555556 -214649.6 -7949.985185 -0.105670   0.259259    12.0 -689452.0  5.368 38.455  9.312    0.647233
