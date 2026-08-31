# XAUUSD prior width vs losses

XAUUSD quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/xauusd/prior_width_study`

What is large? Trade-sample p50=123.6, p75=186.9, p90=252.
Q4_large ~= W in [199.5, 730.6] (28 trades, WR 68%, net $923617).

Skip Q4 counterfactual: keep $162127 (delta $-923617 vs baseline $1085744).

Spearman width↔net: rho=0.24

## By width quartile

 width_q    n  win_rate        net      avg_net     avg_R  stop_rate  loss_n   loss_usd   w_min   w_max    w_med  loss_share
Q1_small 33.0  0.636364   38740.32  1173.949091  0.094098   0.151515    12.0 -379408.76  30.717  79.690  70.0900    0.180111
      Q2 24.0  0.541667 -140468.66 -5852.860833 -0.156098   0.333333    11.0 -473730.06  81.799 123.630 105.0255    0.224886
      Q3 28.0  0.607143  263855.16  9423.398571  0.154587   0.035714    11.0 -495373.28 124.497 186.863 141.7090    0.235161
Q4_large 28.0  0.678571  923616.94 32986.319286  0.222023   0.178571     9.0 -758017.62 199.488 730.620 240.2020    0.359842
