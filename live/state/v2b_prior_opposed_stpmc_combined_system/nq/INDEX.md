# NQ Prior-Opposed ST+PMC + v2b Combined System

**2026-07-15:** gated v2b rows use the **legacy hourly fill-stamp** book (**timestamp-inflated**). Rebuild on resting-limit before portfolio claims.

This is a combined-system audit for the prior-opposed branch. It keeps four views separate:

- `v2b gated only`: actual broker-like v2b `S_1_1_3` fills after prior opposite ST+PMC.
- `prior ST only`: only the specific ST+PMC trades that gated a later v2b campaign.
- `paired prior ST + v2b`: the causal ST+PMC gate trade plus its paired v2b campaign.
- `full ST + gated v2b portfolio`: all `nq_hourly_st_pmc_sl25_tp75_3r` ST+PMC trades plus the gated v2b campaign tape.

| View | Trades | Units | Net | Closed DD | Stress DD | Win % | PF | Max Open Units | Net/Stress |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| v2b gated only | 352 | 1760 | $1184585.00 | $-34652.50 | $-53847.00 | 69.32 | 2.747 | 5 | 22.00 |
| prior ST only | 352 | 352 | $22212.00 | $-9348.00 | $-9348.00 | 28.41 | 1.174 | 1 | 2.38 |
| paired prior ST + v2b | 352 | 2112 | $1206797.00 | $-31191.00 | $-63195.00 | 69.89 | 2.821 | 6 | 19.10 |
| full ST + gated v2b portfolio | 1148 | 2556 | $1272236.14 | $-32923.00 | $-78482.31 | 42.86 | 2.323 | 6 | 16.21 |

Read:

- The paired view answers whether the required prior ST+PMC trade adds or subtracts value around the v2b setup.
- The full portfolio view is the closer deployment proxy if ST+PMC runs continuously and v2b is added only after the prior-opposite condition.
- Stress for combined views is conservative: standalone v2b stress plus the relevant ST+PMC stress/closed-DD budget, so overlap risk is not hidden in this exploratory pass.

Files:

- `summary.csv`
- `paired_trade_contribution.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- [`charts/combined_15m/INDEX.md`](charts/combined_15m/INDEX.md)