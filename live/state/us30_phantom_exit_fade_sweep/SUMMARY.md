# US30 — Phantom-exit fade sweep

Fade the would-be SL/TP of hourly ST+PMC and v2b (do not take the source trade).
Fade risk sweep: 25/75, 40/120, 50/150 (index points). Broker = Engine + PaperBroker.

| family | source | fade | net_usd | stress_dd | N/S | units | wr% |
|---|---|---:|---:|---:|---:|---:|---:|
| v2b_phantom_fade | v2b_prior_opposed | sl50_tp150 | -236 | -1867 | -0.13 | 245 | 25.3 |
| v2b_phantom_fade | v2b_prior_opposed | sl40_tp120 | -730 | -1420 | -0.51 | 260 | 24.2 |
| v2b_phantom_fade | v2b_prior_opposed | sl25_tp75 | -1303 | -1704 | -0.76 | 271 | 21.8 |
| st_pmc_phantom_fade | sl25_tp75_3r | sl40_tp120 | -22782 | -23165 | -0.98 | 1238 | 14.5 |
| st_pmc_phantom_fade | sl25_tp75_3r | sl50_tp150 | -26712 | -27206 | -0.98 | 1197 | 14.8 |
| st_pmc_phantom_fade | sl25_tp75_3r_ma_directional_prior | sl40_tp120 | -18476 | -18794 | -0.98 | 954 | 13.9 |
| st_pmc_phantom_fade | sl25_tp75_3r_ma_directional_prior | sl50_tp150 | -21232 | -21739 | -0.98 | 928 | 14.5 |
| st_pmc_phantom_fade | sl50_tp150_3r | sl40_tp120 | -23212 | -23407 | -0.99 | 1067 | 12.5 |
| st_pmc_phantom_fade | sl50_tp150_3r | sl50_tp150 | -26342 | -26587 | -0.99 | 1053 | 13.4 |
| st_pmc_phantom_fade | sl40_tp120_3r | sl40_tp120 | -22315 | -22548 | -0.99 | 1148 | 13.9 |
| st_pmc_phantom_fade | sl40_tp120_3r | sl50_tp150 | -24469 | -24715 | -0.99 | 1115 | 14.9 |
| st_pmc_phantom_fade | sl25_tp75_3r | sl25_tp75 | -15384 | -15482 | -0.99 | 1313 | 14.9 |
| st_pmc_phantom_fade | sl25_tp75_3r_ma_directional_prior | sl25_tp75 | -11706 | -11860 | -0.99 | 1014 | 15.1 |
| st_pmc_phantom_fade | sl50_tp150_3r | sl25_tp75 | -15909 | -15956 | -1.00 | 1072 | 11.8 |
| st_pmc_phantom_fade | sl40_tp120_3r | sl25_tp75 | -15687 | -15734 | -1.00 | 1154 | 13.0 |

Driver: `live/us30_phantom_exit_fade_sweep.py`
Plugin: `phantom_exit_fade`
