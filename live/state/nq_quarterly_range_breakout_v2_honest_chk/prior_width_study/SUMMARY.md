# Prior width vs losses

NQ quarterly honest breakout (fixed cancel path): prior-range width vs losses.

Hub: /home/tester/hsm/potions/live/state/nq_quarterly_range_breakout_v2_honest_chk/prior_width_study/

What is large? Trade-sample p50=646, p75=1734, p90=2931 pts.

## By width quartile

 width_q    n  win_rate       net      avg_net    avg_R  stop_rate  loss_n  loss_usd   w_min   w_max   w_med  loss_share
Q1_small 21.0  0.619048   49400.0  2352.380952 0.035125   0.380952     8.0 -150716.0  130.75  347.25  292.25    0.105762
      Q2 19.0  0.684211   99659.0  5245.210526 0.181812   0.157895     6.0 -196210.0  357.75  628.00  459.50    0.137687
      Q3 20.0  0.550000  -22927.0 -1146.350000 0.023616   0.250000     9.0 -617742.0  664.00 1693.25 1157.75    0.433489
Q4_large 20.0  0.750000 1311726.0 65586.300000 0.275146   0.100000     5.0 -460380.0 1854.25 6474.75 2696.00    0.323063

Spearman width↔net=0.33, width↔R=-0.00
Skip Q4 net=126132 (vs baseline 1437858)
Skip ≥p75 net=126132
