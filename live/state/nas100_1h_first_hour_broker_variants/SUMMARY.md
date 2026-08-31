# NAS100 first-hour broker-like variants

Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.
Realism: slip 1 tick, spread, fee $1.50/unit, NAS100 $1/pt (CFD).

**How / why (shared):** [`../nq_1h_first_hour_broker_variants/MECHANICS.md`](../nq_1h_first_hour_broker_variants/MECHANICS.md)

| Book | Trades | WR | Net | Stress | N/S | entries | stop | tp | eod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline SL=open TP=3×body 1-lot | 2213 | 37.6% | $7,728 | $-1,889 | **4.09** | 2267 | 1197 | 272 | 753 |
| half-body SL + 3R 1-lot | 2247 | 30.0% | $4,505 | $-1,524 | 2.96 | 2262 | 1523 | 435 | 292 |
| retrace body 72% → SL extreme → 3R | 1465 | 34.3% | $1,265 | $-3,854 | 0.33 | 1496 | 854 | 206 | 414 |
| 0.75-body SL + 1R/2R/3R ladder 3-lot | 2255 | 40.4% | $11,408 | $-5,583 | 2.04 | 2266 | 1360 | 1935 | 518 |

## Stance

Same rank order as NQ: **baseline 3×body best N/S**, ladder highest dollars, retrace reject.
Shorter CFD tape (~174k RTH 5m bars) → fewer trades than NQ; $1/pt → smaller USD nets.
**RETAIN** baseline as NAS100 first-hour mirror (not demoed).

Hub: `live/state/nas100_1h_first_hour_broker_variants/`
