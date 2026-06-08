# MES Hourly ST + PMC close_against_entry_next_open (StrategyPlugin)

| Metric | Value |
|---|---:|
| Source | `potions/live/state/hourly_st_pmc_strategyplugin_variants_cross_market/mes/combined_state/fills.csv` |
| Bar source | `/home/tester/hsm/potions/mes/mes_1min_raw.csv` |
| Bar window | `2019-05-05T18:00:00-04:00` to `2023-08-17T08:00:00-04:00` |
| Units | 333 |
| Trade groups | 333 |
| Winning units | 30 |
| Losing units | 303 |
| Net points | 1204.99 |
| Point value | $5.00 |
| Net dollars | $5,525.45 |
| Close MTM DD | $-2,385.17 |
| Intrabar stress MTM DD | $-2,393.92 |
| Max open units | 1 |
| Net / intrabar stress DD | 2.31 |

Notes: Combined multi-strategy Engine + PaperBroker StrategyPlugin replay. Variant=close_against_entry_next_open; stop=50; target=150; tp1_qty=1; runner_qty=0; runner_target=None; ma_filter=none; close_against=True; st_flip_exit=False; pmc_cross_exit=False; slippage=1 tick; fee=$1.50/unit.
