# EURUSD prior width vs losses

EURUSD quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/eurusd/prior_width_study`

What is large? Trade-sample p50=0.06953, p75=0.09292, p90=0.1212.
Q4_large ~= W in [0.09426, 0.2161] (27 trades, WR 44%, net $-78715).

Skip Q4 counterfactual: keep $217080 (delta $78715 vs baseline $138365).

Spearman width↔net: rho=0.04

## By width quartile

 width_q    n  win_rate      net      avg_net     avg_R  stop_rate  loss_n  loss_usd   w_min   w_max    w_med  loss_share
Q1_small 31.0  0.483871  19983.2   644.619355 -0.009828   0.354839    16.0 -192308.4 0.03049 0.04914 0.041440    0.196469
      Q2 25.0  0.560000  23941.4   957.656000  0.041757   0.280000    11.0 -190530.4 0.04935 0.06953 0.056550    0.194653
      Q3 28.0  0.571429 173155.4  6184.121429  0.186339   0.142857    12.0 -185609.0 0.07011 0.09292 0.080055    0.189625
Q4_large 27.0  0.444444 -78715.0 -2915.370370 -0.062371   0.222222    15.0 -410373.0 0.09426 0.21611 0.113310    0.419252
