# Broker-Like Bar Replay Rankings

New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | ES Monthly ORB restricted scaleout3 boundary-stop entry | ES | 12 | 4 | $281,075.00 | $-62,075.00 | $-66,162.50 | 3 | 4.25 |
| 2 | ES Monthly ORB restricted scaleout3 | ES | 54 | 18 | $246,453.12 | $-62,075.00 | $-66,162.50 | 3 | 3.72 |
| 3 | NQ Monthly ORB restricted scaleout3 boundary-stop entry | NQ | 18 | 6 | $446,207.50 | $-117,565.00 | $-122,080.00 | 3 | 3.66 |
| 4 | NQ Monthly ORB restricted scaleout3 | NQ | 30 | 10 | $430,465.00 | $-117,565.00 | $-122,080.00 | 3 | 3.53 |
| 5 | YM Monthly ORB restricted scaleout3 | YM | 54 | 18 | $179,658.75 | $-56,275.00 | $-56,795.00 | 3 | 3.16 |
| 6 | MNQ Monthly ORB restricted scaleout3 boundary-stop entry | MNQ | 15 | 5 | $37,605.50 | $-11,756.00 | $-12,208.50 | 3 | 3.08 |
| 7 | MES Monthly ORB restricted scaleout3 | MES | 24 | 8 | $2,901.88 | $-7,821.25 | $-8,350.00 | 3 | 0.35 |
| 8 | MNQ Monthly ORB restricted scaleout3 | MNQ | 108 | 36 | $2,425.62 | $-34,230.12 | $-34,398.12 | 3 | 0.07 |
| 9 | MYM Monthly ORB restricted scaleout3 | MYM | 108 | 36 | $-724.50 | $-15,699.50 | $-16,356.50 | 3 | -0.04 |
| 10 | MES Monthly ORB restricted scaleout3 boundary-stop entry | MES | 21 | 7 | $-17,611.88 | $-38,936.25 | $-39,266.25 | 3 | -0.45 |
| 11 | MYM Monthly ORB restricted scaleout3 boundary-stop entry | MYM | 18 | 6 | $-27,342.75 | $-48,244.50 | $-48,570.00 | 3 | -0.56 |
| 12 | YM Monthly ORB restricted scaleout3 boundary-stop entry | YM | 6 | 2 | $-602,942.50 | $-612,810.00 | $-616,650.00 | 3 | -0.98 |

## Coverage Notes

- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.
- v2b clean-break variants now have a 5m StrategyPlugin pass at `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`; broad bullish clean-break is positive, but does not outrank hardened v2b OCO on MNQ.
- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.
