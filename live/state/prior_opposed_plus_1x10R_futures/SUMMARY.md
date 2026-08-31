# Prior-opposed S_1_1_3 + 1×10R (futures StrategyPlugin)

Book: 1 TP1 + 1 TP2 + 3 EOD runners + **1 runner @ 10×R** (BE after TP1).
Gate: resting_limit prior-opposed. Plugin: `v2b_scaleout`.

| market | trades | net | stress | N/S | causality |
|---|---:|---:|---:|---:|---:|
| `nq` | 433 | $1618268 | $-82788 | **19.55** | 0 |
| `mnq` | 429 | $156157 | $-8399 | **18.59** | 0 |
| `ym` | 437 | $344016 | $-40672 | **8.46** | 0 |

Compare to baseline S_1_1_3 hubs and post-process `prior_opposed_10r_addon/`.

