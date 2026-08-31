# Post-entry SMT — SPX500 primary / NAS100 peer

Level family: CHOP20 active range (frozen at primary break / signal available_at).
Windows: fast 0–5m, late 6–30m, expiry min(exit, +60m).

## State counts

    confirmation_class  n    share     net_R  median_R    mean_R  profit_factor  win_rate  stop_rate  hit_0_5R   hit_1R   hit_4R  median_MAE_R  p90_MAE_R  median_MFE_R  N_over_stress  median_hold_min  median_peer_delay_min
     ALREADY_CONFIRMED 24 0.428571  1.497669 -0.277666  0.062403       1.069759  0.291667   0.833333  0.333333 0.208333 0.166667     -0.161541  -0.030582      0.261851       0.069759           4460.0                -1064.0
            NO_CONFIRM 19 0.339286 10.975338 -0.252809  0.577649       2.392729  0.368421   0.842105  0.421053 0.368421 0.105263     -0.213277  -0.057577      0.332205       1.392729           2037.0                    NaN
PEER_LEVEL_UNAVAILABLE 13 0.232143 -0.928705 -0.383959 -0.071439       0.884361  0.307692   0.923077  0.307692 0.153846 0.076923     -0.141638  -0.083881      0.151877      -0.115639            994.0                    NaN

## Stance (descriptive)

- **ALREADY_CONFIRMED** n=24 share=43% stop=83% mean_R=+0.06 N/stress=0.07
- **NO_CONFIRM** n=19 share=34% stop=84% mean_R=+0.58 N/stress=1.39

ALREADY_CONFIRMED stop_rate=83% (sync reference).

Hub: `/home/tester/hsm/potions/live/state/chop20_post_entry_smt_nas100_spx500/spx500_vs_nas100`
