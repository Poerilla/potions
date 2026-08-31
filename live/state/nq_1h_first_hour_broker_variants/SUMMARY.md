# NQ first-hour broker-like variants

Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.
Realism: slip 1 tick, spread, fee $1.50/unit, NQ $20/pt.

**How / why:** [`MECHANICS.md`](MECHANICS.md) — open-continuation after the RTH first hour; **3× body TP** is the efficiency book.

| Book | Trades | WR | Net | Stress | N/S | entries | stop | tp | eod | vs diag N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline SL=open TP=3×body 1-lot | 3943 | 37.2% | $176,743 | $-31,718 | **5.57** | 4028 | 2143 | 518 | 1296 | 9.32 |
| half-body SL + 3R 1-lot | 3952 | 30.4% | $118,693 | $-25,022 | 4.74 | 3976 | 2663 | 769 | 526 | 10.01 |
| retrace body 72% → SL extreme → 3R | 2625 | 33.3% | $29,919 | $-89,667 | 0.33 | 2670 | 1564 | 357 | 720 | 2.22 |
| 0.75-body SL + 1R/2R/3R ladder 3-lot | 3958 | 40.4% | $360,597 | $-91,267 | 3.95 | 3976 | 2391 | 3375 | 924 | 7.64 |

## Stance

- **RETAIN** baseline **SL=open / TP=3×body** as the primary first-hour sleeve (best N/S).
- Ladder: retain for absolute dollars only; worse N/S than 1-lot baseline.
- Half-body: secondary; still green.
- Retrace 72%: **reject**.
- Not a peer of prior-opposed / ST+PMC on N/S, but a **good capital-efficient daily book** outside those.

## Notes

- Baseline / half-body: `market_close` entry on 10:25 bar; protective **stop** + TP **limit**.
- Retrace 72%: resting **limit** entry; cancel if FH extreme swept before fill; then stop+TP.
- 0.75-body ladder: 3-lot entry; stop @ 0.75×body; 1-lot limits @ 1R/2R/3R (no OCO across rungs).
- Diagnostic refs overstate N/S; broker haircut is expected (~40% on baseline).

NAS100 mirror: [`../nas100_1h_first_hour_broker_variants/SUMMARY.md`](../nas100_1h_first_hour_broker_variants/SUMMARY.md).

Hub: `live/state/nq_1h_first_hour_broker_variants/`
