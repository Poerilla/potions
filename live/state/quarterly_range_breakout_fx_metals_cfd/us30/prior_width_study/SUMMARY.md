# US30 prior width vs losses

US30 quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/us30/prior_width_study`

What is large? Trade-sample p50=2802, p75=3558, p90=4974.
Q4_large ~= W in [3656, 7678] (12 trades, WR 75%, net $79837).

Skip Q4 counterfactual: keep $-7788 (delta $-79837 vs baseline $72048).

Spearman width↔net: rho=0.18

## By width quartile

 width_q    n  win_rate       net      avg_net     avg_R  stop_rate  loss_n  loss_usd  w_min  w_max  w_med  loss_share
Q1_small 12.0  0.833333  23519.20  1959.933333  0.505121   0.166667     2.0   -9368.8  884.0 2026.0 1149.0    0.048824
      Q2 12.0  0.500000  -7063.80  -588.650000 -0.058077   0.500000     6.0  -47775.6 2069.0 2743.0 2426.0    0.248977
      Q3 12.0  0.416667 -24243.60 -2020.300000 -0.162806   0.416667     7.0  -79641.2 2862.0 3525.0 2990.0    0.415041
Q4_large 12.0  0.750000  79836.56  6653.046667  0.250325   0.083333     3.0  -55102.0 3656.0 7677.6 4634.0    0.287158
