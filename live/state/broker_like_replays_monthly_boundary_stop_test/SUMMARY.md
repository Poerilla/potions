# Broker-Like Bar Replay Rankings

New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | YM Monthly ORB restricted scaleout3 boundary-stop entry | YM | 1296 | 432 | $359,526.25 | $-45,127.50 | $-47,753.75 | 3 | 7.53 |
| 2 | MYM Monthly ORB restricted scaleout3 boundary-stop entry | MYM | 564 | 188 | $21,353.25 | $-4,626.62 | $-5,504.12 | 3 | 3.88 |
| 3 | ES Monthly ORB restricted scaleout3 boundary-stop entry | ES | 1281 | 427 | $370,559.38 | $-78,693.75 | $-95,793.75 | 3 | 3.87 |
| 4 | NQ Monthly ORB restricted scaleout3 boundary-stop entry | NQ | 1284 | 428 | $566,330.00 | $-156,561.25 | $-168,163.75 | 3 | 3.37 |
| 5 | MES Monthly ORB restricted scaleout3 boundary-stop entry | MES | 333 | 111 | $22,186.56 | $-6,030.94 | $-7,267.19 | 3 | 3.05 |
| 6 | MNQ Monthly ORB restricted scaleout3 boundary-stop entry | MNQ | 552 | 184 | $45,331.62 | $-15,719.00 | $-16,881.38 | 3 | 2.69 |

## Coverage Notes

- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.
- v2b clean-break variants need a 1m/5m StrategyPlugin before they can be compared in this broker-like table.
- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.
