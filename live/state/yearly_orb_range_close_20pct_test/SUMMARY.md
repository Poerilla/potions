# Broker-Like Bar Replay Rankings

New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ Yearly ORB scaleout3 20% range-close | NQ | 138 | 46 | $743,876.25 | $-127,940.00 | $-141,210.00 | 3 | 5.27 |
| 2 | MNQ Yearly ORB scaleout3 20% range-close | MNQ | 30 | 10 | $66,913.25 | $-12,785.00 | $-14,141.00 | 3 | 4.73 |
| 3 | ES Yearly ORB scaleout3 20% range-close | ES | 165 | 55 | $366,593.75 | $-75,937.50 | $-85,700.00 | 3 | 4.28 |
| 4 | YM Yearly ORB scaleout3 20% range-close | YM | 147 | 49 | $187,615.00 | $-61,390.00 | $-63,535.00 | 3 | 2.95 |
| 5 | MYM Yearly ORB scaleout3 20% range-close | MYM | 42 | 14 | $12,196.62 | $-5,948.50 | $-6,092.50 | 3 | 2.00 |
| 6 | MES Yearly ORB scaleout3 20% range-close | MES | 33 | 11 | $10,495.31 | $-7,597.50 | $-8,497.50 | 3 | 1.24 |

## Coverage Notes

- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.
- v2b clean-break variants need a 1m/5m StrategyPlugin before they can be compared in this broker-like table.
- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.
