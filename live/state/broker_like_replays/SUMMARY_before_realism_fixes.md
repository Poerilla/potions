# Broker-Like Bar Replay Rankings

New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ ATR daily ladder 1/1/2/2/2 10-max | NQ | 402 | 149 | $1,576,610.00 | $-235,800.00 | $-255,950.00 | 10 | 6.16 |
| 2 | MNQ ATR daily ladder 1/1/2/2/2 10-max | MNQ | 162 | 52 | $147,280.00 | $-23,408.50 | $-25,610.00 | 10 | 5.75 |
| 3 | NQ ATR daily 3-initial 10-max | NQ | 623 | 149 | $1,723,980.00 | $-299,280.00 | $-308,655.00 | 10 | 5.59 |
| 4 | MNQ ATR daily 3-initial 10-max | MNQ | 233 | 52 | $160,401.50 | $-28,647.50 | $-29,264.00 | 10 | 5.48 |
| 5 | ES ATR weekly 2-initial / 3-add / 6-max | ES | 144 | 43 | $857,100.00 | $-194,325.00 | $-199,637.50 | 6 | 4.29 |
| 6 | ES Monthly ORB restricted scaleout3 | ES | 54 | 18 | $246,453.12 | $-62,075.00 | $-66,162.50 | 3 | 3.72 |
| 7 | NQ Monthly ORB restricted scaleout3 | NQ | 30 | 10 | $430,465.00 | $-117,565.00 | $-122,080.00 | 3 | 3.53 |
| 8 | NQ ATR weekly 2-initial / 3-add / 6-max | NQ | 127 | 38 | $1,444,735.00 | $-407,105.00 | $-428,375.00 | 6 | 3.37 |
| 9 | YM Monthly ORB restricted scaleout3 | YM | 54 | 18 | $179,658.75 | $-56,275.00 | $-56,795.00 | 3 | 3.16 |
| 10 | NQ Yearly ORB scaleout3 | NQ | 204 | 68 | $403,571.25 | $-125,490.00 | $-133,860.00 | 3 | 3.01 |
| 11 | MNQ Yearly ORB scaleout3 | MNQ | 72 | 24 | $39,216.62 | $-12,546.00 | $-13,378.50 | 3 | 2.93 |
| 12 | MNQ ATR weekly 2-initial / 3-add / 6-max | MNQ | 54 | 17 | $119,427.00 | $-40,691.50 | $-42,806.50 | 6 | 2.79 |
| 13 | MES ATR weekly 2-initial / 3-add / 6-max | MES | 28 | 8 | $37,548.75 | $-14,457.50 | $-17,212.50 | 6 | 2.18 |
| 14 | ES ATR daily 3-initial 10-max | ES | 628 | 147 | $589,050.00 | $-271,925.00 | $-275,712.50 | 10 | 2.14 |
| 15 | ES ATR daily ladder 1/1/2/2/2 10-max | ES | 416 | 147 | $464,712.50 | $-238,925.00 | $-245,025.00 | 10 | 1.90 |
| 16 | YM ATR daily 3-initial 10-max | YM | 609 | 144 | $297,045.00 | $-161,975.00 | $-165,935.00 | 10 | 1.79 |
| 17 | YM ATR weekly 2-initial / 3-add / 6-max | YM | 157 | 49 | $407,900.00 | $-231,360.00 | $-245,550.00 | 6 | 1.66 |
| 18 | MYM ATR weekly 2-initial / 3-add / 6-max | MYM | 83 | 27 | $24,931.00 | $-18,860.50 | $-18,929.50 | 6 | 1.32 |
| 19 | MYM ATR daily 3-initial 10-max | MYM | 249 | 58 | $16,639.00 | $-12,145.50 | $-13,205.50 | 10 | 1.26 |
| 20 | YM Yearly ORB scaleout3 | YM | 243 | 81 | $59,582.50 | $-70,715.00 | $-75,305.00 | 3 | 0.79 |
| 21 | ES Yearly ORB scaleout3 | ES | 219 | 73 | $41,684.38 | $-64,500.00 | $-70,612.50 | 3 | 0.59 |
| 22 | YM ATR daily ladder 1/1/2/2/2 10-max | YM | 408 | 144 | $105,555.00 | $-222,215.00 | $-224,330.00 | 10 | 0.47 |
| 23 | MES Monthly ORB restricted scaleout3 | MES | 24 | 8 | $2,901.88 | $-7,821.25 | $-8,350.00 | 3 | 0.35 |
| 24 | MYM ATR daily ladder 1/1/2/2/2 10-max | MYM | 173 | 58 | $2,799.00 | $-19,091.50 | $-19,514.50 | 10 | 0.14 |
| 25 | MYM Yearly ORB scaleout3 | MYM | 81 | 27 | $677.38 | $-5,097.00 | $-5,407.50 | 3 | 0.13 |
| 26 | MES ATR daily 3-initial 10-max | MES | 169 | 40 | $3,008.75 | $-27,167.50 | $-27,550.00 | 10 | 0.11 |
| 27 | MNQ Monthly ORB restricted scaleout3 | MNQ | 108 | 36 | $2,425.62 | $-34,230.12 | $-34,398.12 | 3 | 0.07 |
| 28 | MYM Monthly ORB restricted scaleout3 | MYM | 108 | 36 | $-222.00 | $-15,443.88 | $-16,100.88 | 3 | -0.01 |
| 29 | MES ATR daily ladder 1/1/2/2/2 10-max | MES | 111 | 40 | $-1,192.50 | $-23,878.75 | $-24,488.75 | 10 | -0.05 |
| 30 | MES Yearly ORB scaleout3 | MES | 36 | 12 | $-3,465.00 | $-6,480.00 | $-7,143.75 | 3 | -0.49 |

## Coverage Notes

- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.
- v2b clean-break variants now have a 5m StrategyPlugin pass at `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`; broad bullish clean-break is the only one that remains interesting, but it still trails hardened v2b OCO on MNQ.
- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.
