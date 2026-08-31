# NAS100 prior width vs losses

NAS100 quarterly honest breakout (mid SL): prior-range width vs outcomes.

Hub: `live/state/quarterly_range_breakout_fx_metals_cfd/nas100/prior_width_study`

What is large? Trade-sample p50=1512, p75=2578, p90=3203.
Q4_large ~= W in [2600, 6417] (12 trades, WR 75%, net $65924).

Skip Q4 counterfactual: keep $30219 (delta $-65924 vs baseline $96143).

Spearman width↔net: rho=0.31

## By width quartile

 width_q    n  win_rate      net     avg_net     avg_R  stop_rate  loss_n  loss_usd  w_min  w_max  w_med  loss_share
Q1_small 13.0  0.846154  7009.32  539.178462  5.385705   0.076923     2.0 -10911.60   10.7  721.3  567.4    0.183660
      Q2 13.0  0.538462 -3925.24 -301.941538 -0.044128   0.307692     6.0 -22555.56  820.3 1511.6 1252.4    0.379646
      Q3 11.0  0.818182 27135.28 2466.843636  0.274953   0.090909     2.0  -9669.72 1688.8 2577.7 2306.9    0.162757
Q4_large 12.0  0.750000 65923.98 5493.665000  0.295056   0.166667     3.0 -16275.20 2599.7 6417.0 3140.4    0.273938
