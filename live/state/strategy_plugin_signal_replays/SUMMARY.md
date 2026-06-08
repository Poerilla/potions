# StrategyPlugin Signal Replay Rankings

These rows are true `StrategyPlugin` passes through `Engine` + `PaperBroker`, not direct research CSV replays. Open positions are marked at the final replay close so live-style stack heat is visible.

| Rank | Candidate | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | ATR daily ladder 1/1/2/2/2 / 10-max | 162 | 52 | $147,280.00 | $-23,408.50 | $-25,610.00 | 10 | 5.75 |
| 2 | ATR daily 3-initial / 1-add / 10-max | 233 | 52 | $160,401.50 | $-28,647.50 | $-29,264.00 | 10 | 5.48 |
| 3 | Yearly ORB scaleout3 live-runtime replay | 72 | 24 | $39,216.62 | $-12,546.00 | $-13,378.50 | 3 | 2.93 |
| 4 | ATR weekly 2-initial / 3-add / 6-max | 54 | 17 | $119,427.00 | $-40,691.50 | $-42,806.50 | 6 | 2.79 |
| 5 | ATR weekly 3-initial / 1-add / 10-max | 84 | 17 | $152,430.50 | $-76,638.50 | $-80,653.00 | 10 | 1.89 |
| 6 | ATR weekly ladder 1/1/2/2/2 / 10-max | 61 | 17 | $146,241.00 | $-75,065.00 | $-81,597.50 | 10 | 1.79 |
| 7 | ATR daily weekly-flat 5-max | 103 | 28 | $33,721.00 | $-22,849.50 | $-23,466.00 | 5 | 1.44 |

## Not Yet Promoted To Signal Replay

- Monthly ORB restricted scaleout3 is still a research/artifact replay until its live plugin is implemented.
- Monthly overlap range breakout daily-ST retest x5 is still a 4h research/artifact replay until its live plugin is implemented.
- v2b clean-break variants now have a 5m StrategyPlugin pass at `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`; broad bullish clean-break is positive, but does not outrank hardened v2b OCO on MNQ.
