# NQ first-hour follow 3R (broker-like)

Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.
Entry: `market_close` on last FH bar (10:25); SL = FH open; TP = 3× body; flatten 15:59.
Realism: slip 1 tick, spread model, fee $1.50/unit, NQ $20/pt.

| Book | Trades | WR | Net | Stress DD | N/S | vs diag n | vs diag net |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R all first-hour | 3943 | 37.2% | $176,743 | $-31,718 | 5.57 | 3968 | $-66265 |
| follow 3R first-hour body=strong | 1102 | 51.4% | $127,212 | $-31,945 | 3.98 | 1125 | — |

## Diagnostic reference (pandas walk)

- follow 3R all: n=3968 WR=38.2% net=$243008 N/S=9.32
- follow 3R body=strong: n=1125 WR lift=+14.4pp avg lift=$+72 N/S=6.11

Stance: promotion candidate only if broker-like N/S stays healthy vs diagnostic.
