# Post-entry SMT — NAS100 primary / SPX500 peer

Level family: CHOP20 active range (frozen at primary break / signal available_at).
Windows: fast 0–5m, late 6–30m, expiry min(exit, +60m).

## State counts

confirmation_class  n    share     net_R  median_R    mean_R  profit_factor  win_rate  stop_rate  hit_0_5R   hit_1R   hit_4R  median_MAE_R  p90_MAE_R  median_MFE_R  N_over_stress  median_hold_min  median_peer_delay_min
        NO_CONFIRM 45 0.608108 25.664820 -0.126356  0.570329       2.347445  0.288889   0.844444  0.377778 0.266667 0.155556     -0.138199  -0.011299      0.261819       1.347445           3518.0                    NaN
 ALREADY_CONFIRMED 28 0.378378 -2.094025 -0.249418 -0.074787       0.878050  0.214286   0.928571  0.357143 0.214286 0.071429     -0.186277  -0.049893      0.177096      -0.121950           4688.5                 -975.5
    OPPOSITE_BREAK  1 0.013514  1.160083  1.160083  1.160083            NaN  1.000000   1.000000  1.000000 1.000000 0.000000     -0.336857  -0.336857      1.245063            NaN          12201.0                    NaN

## Stance (descriptive)

- **NO_CONFIRM** n=45 share=61% stop=84% mean_R=+0.57 N/stress=1.35
- **ALREADY_CONFIRMED** n=28 share=38% stop=93% mean_R=-0.07 N/stress=-0.12
- **OPPOSITE_BREAK** n=1 share=1% stop=100% mean_R=+1.16 N/stress=n/a

ALREADY_CONFIRMED stop_rate=93% (sync reference).

Hub: `/home/tester/hsm/potions/live/state/chop20_post_entry_smt_nas100_spx500/nas100_vs_spx500`
