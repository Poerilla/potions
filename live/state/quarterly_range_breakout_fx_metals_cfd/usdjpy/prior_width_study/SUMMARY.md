# USDJPY prior width vs losses

USDJPY quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/usdjpy/prior_width_study`

What is large? Trade-sample p50=5.943, p75=8.993, p90=11.31.
Q4_large ~= W in [9.01, 21.38] (27 trades, WR 44%, net $-4315036).

Skip Q4 counterfactual: keep $4273260 (delta $4315036 vs baseline $-41776).

Spearman width↔net: rho=0.01

## By width quartile

 width_q    n  win_rate        net        avg_net     avg_R  stop_rate  loss_n    loss_usd  w_min  w_max   w_med  loss_share
Q1_small 28.0  0.571429   470248.0   16794.571429  0.029965   0.285714    12.0 -16560728.0  2.952  4.070  3.3060    0.147218
      Q2 28.0  0.535714 -3855372.0 -137691.857143 -0.069997   0.392857    13.0 -24208732.0  4.165  5.930  4.9665    0.215205
      Q3 29.0  0.655172  7658384.0  264082.206897  0.096134   0.241379    10.0 -27398360.0  5.956  8.993  7.5900    0.243560
Q4_large 27.0  0.444444 -4315036.0 -159816.148148 -0.020768   0.259259    15.0 -44323508.0  9.010 21.375 11.1590    0.394017

_Note: USDJPY P&L uses repo POINT_VALUES convention (JPY per 1.0 move); cross-market $ ranks are indicative._