# MNQ Prior-Opposed ST+PMC + v2b Combined System

**Full stats doc:** [`MNQ_prior-opposed_ST+PMC_to_v2b.md`](MNQ_prior-opposed_ST+PMC_to_v2b.md)

This is a combined-system audit for the prior-opposed branch. It keeps four views separate:

- `v2b gated only`: actual broker-like v2b `S_1_1_3` fills after prior opposite ST+PMC.
- `prior ST only`: only the specific ST+PMC trades that gated a later v2b campaign.
- `paired prior ST + v2b`: the causal ST+PMC gate trade plus its paired v2b campaign.
- `full ST + gated v2b portfolio`: all `mnq_hourly_st_pmc_sl25_tp75_3r` ST+PMC trades plus the gated v2b campaign tape.

| View | Trades | Units | Net | Closed DD | Stress DD | Win % | PF | Max Open Units | Net/Stress |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v2b gated only | 353 | 1765 | $113547.50 | $-3493.50 | $-5418.00 | 68.56 | 2.615 | 5 | 20.96 |
| prior ST only | 353 | 353 | $1894.50 | $-1085.50 | $-1085.50 | 28.61 | 1.145 | 1 | 1.75 |
| paired prior ST + v2b | 353 | 2118 | $115442.00 | $-3159.50 | $-6503.50 | 68.56 | 2.676 | 6 | 17.75 |
| full ST + gated v2b portfolio | 1144 | 2556 | $122424.62 | $-3397.50 | $-7880.00 | 43.18 | 2.238 | 6 | 15.54 |

Read:

- The paired view answers whether the required prior ST+PMC trade adds or subtracts value around the v2b setup.
- The full portfolio view is the closer deployment proxy if ST+PMC runs continuously and v2b is added only after the prior-opposite condition.
- Stress for combined views is conservative: standalone v2b stress plus the relevant ST+PMC stress/closed-DD budget, so overlap risk is not hidden in this exploratory pass.

Files:

- `summary.csv`
- `paired_trade_contribution.csv`
- `states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- [`charts/combined_15m/INDEX.md`](charts/combined_15m/INDEX.md)