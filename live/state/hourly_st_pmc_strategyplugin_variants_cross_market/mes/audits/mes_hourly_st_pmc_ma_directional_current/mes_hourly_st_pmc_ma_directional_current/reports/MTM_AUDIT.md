# MES Hourly ST + PMC ma_directional_current (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `potions/live/state/hourly_st_pmc_strategyplugin_variants_cross_market/mes/combined_state/fills.csv` |
| Bar source | `/home/tester/hsm/potions/mes/mes_1min_raw.csv` |
| Bar window | `2019-05-05T18:00:00-04:00` to `2023-08-17T08:00:00-04:00` |
| Units | 150 |
| Trade groups | 150 |
| Winning units | 39 |
| Losing units | 111 |
| Net points | 272.25 |
| Point value | $5.00 |
| Net dollars | $1,136.25 |
| Close MTM DD | $-6,103.62 |
| Intrabar stress MTM DD | $-6,134.87 |
| Max open units | 1 |
| Net / intrabar stress DD | 0.19 |

Notes: Combined multi-strategy Engine + PaperBroker StrategyPlugin replay. Variant=ma_directional_current; stop=50; target=150; tp1_qty=1; runner_qty=0; runner_target=None; ma_filter=directional_current; close_against=False; st_flip_exit=False; pmc_cross_exit=False; slippage=1 tick; fee=$1.50/unit.
