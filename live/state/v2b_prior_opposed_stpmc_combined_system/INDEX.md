# Prior-Opposed ST+PMC + v2b Combined System

Combined-system audit for MNQ and NQ. The gated v2b leg is the same `S_1_1_3` prior-opposed rule; ST+PMC is the same-market `sl25_tp75_3r` candidate.

**2026-07-15:** NQ rows below use the **legacy hourly fill-stamp** gated v2b book (**timestamp-inflated**). Rebuild combined views on NQ **resting-limit** ([`../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md)) before portfolio claims.

| Market | View | Trades | Net | Stress DD | Max Open Units | PF | Net/Stress |
|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | v2b gated only | 353 | $113547.50 | $-5418.00 | 5 | 2.615 | 20.96 |
| MNQ | prior ST only | 353 | $1894.50 | $-1085.50 | 1 | 1.145 | 1.75 |
| MNQ | paired prior ST + v2b | 353 | $115442.00 | $-6503.50 | 6 | 2.676 | 17.75 |
| MNQ | full ST + gated v2b portfolio | 1144 | $122424.62 | $-7880.00 | 6 | 2.238 | 15.54 |
| NQ | v2b gated only | 352 | $1184585.00 | $-53847.00 | 5 | 2.747 | 22.00 |
| NQ | prior ST only | 352 | $22212.00 | $-9348.00 | 1 | 1.174 | 2.38 |
| NQ | paired prior ST + v2b | 352 | $1206797.00 | $-63195.00 | 6 | 2.821 | 19.10 |
| NQ | full ST + gated v2b portfolio | 1148 | $1272236.14 | $-78482.31 | 6 | 2.323 | 16.21 |

Market reports:

- [MNQ](mnq/INDEX.md)
- [NQ](nq/INDEX.md)