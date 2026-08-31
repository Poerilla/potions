# AUDJPY prior width vs losses

AUDJPY quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/audjpy/prior_width_study`

What is large? Trade-sample p50=6.824, p75=9.929, p90=13.17.
Q4_large ~= W in [10.01, 23.05] (30 trades, WR 37%, net $-27323520).

Skip Q4 counterfactual: keep $397700 (delta $27323520 vs baseline $-26925820).

Spearman width↔net: rho=-0.14

## By width quartile

 width_q    n  win_rate         net        avg_net     avg_R  stop_rate  loss_n    loss_usd  w_min  w_max  w_med  loss_share
Q1_small 30.0  0.566667   3961380.0  132046.000000  0.005612   0.300000    13.0 -17491412.0  2.196  4.724  4.105    0.135214
      Q2 29.0  0.586207   -111956.0   -3860.551724 -0.004586   0.275862    12.0 -23143028.0  4.752  6.791  5.134    0.178903
      Q3 29.0  0.586207  -3451724.0 -119024.965517 -0.009094   0.172414    12.0 -32254276.0  6.857  9.686  7.968    0.249336
Q4_large 30.0  0.366667 -27323520.0 -910784.000000 -0.216933   0.266667    19.0 -56471976.0 10.010 23.050 12.374    0.436547
