# Orphan / non-strategy LIMIT fill PL attribution

**As of:** 2026-08-18  
**Definition:** Broker `ORDER_FILL`s on trades that opened **without** a matching
`live/demo/*_oanda/state/fills.csv` row (same instrument, side, qty, within ±2 minutes).
Closing fills of those `tradeID`s are included. OANDA `clientExtensions.tag` is usually
empty, so demo-tape match is the practical “strategy vs non-strat” split.

## Headline

| Scope | Non-strat net PL | Strat-matched net PL | All fill PL |
|---|---:|---:|---:|
| Full transaction dump | **$-2,600.06** | $2,523.17 | $-76.89 |
| Since Mon 2026-08-17 | **$-1,873.96** | $0.00 | $-1,873.96 |

### Non-strat since Mon (the orphan LIMIT week)

- Opens: 28 · closing fills with PL: 28
- Wins: 0 / $0.00
- Losses: 28 / $-1,873.96
- By instrument: {'US30_USD': -1197.8664999999999, 'NAS100_USD': -676.0984000000001}
- By reason: {'STOP_LOSS_ORDER': -1844.8158999999998, 'MARKET_ORDER': -29.149, 'LIMIT_ORDER': 0.0}

Almost all of this week’s orphan closes were **STOP_LOSS_ORDER** (~50pt) after untagged
LIMIT entries; **−$29.15** is the MonOR market that closed an orphan long (not a true short open).

### Note on the 53 cancelled pendings

Those orders were still **PENDING** at mass-cancel — **0 fills** from that id set.
Non-strat PnL is from **earlier** filled sibling rests of the same class.

Artifact: [`ORPHAN_FILL_PL_ATTRIBUTION.json`](ORPHAN_FILL_PL_ATTRIBUTION.json)
