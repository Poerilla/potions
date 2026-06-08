# Live Replay Candidate MTM Audit

This is a flat-file replay/audit of the current leading candidates. Yearly ORB uses true `PaperBroker` fills from the live runtime. The other rows replay existing unit-level research artifacts through the same MTM calculator until their strategy plugins are implemented.

| Candidate | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Yearly ORB scaleout3 live-runtime replay | 72 | 24 | $39,216.62 | $-12,546.00 | $-13,378.50 | 3 | 2.93 |
| ATR Supertrend weekly-primary 10max 3-initial | 226 | 49 | $303,214.00 | $-18,681.00 | $-20,383.50 | 10 | 14.88 |
| ATR Supertrend weekly-primary 10max ladder 1/1/2/2/2 | 161 | 49 | $263,784.50 | $-17,120.00 | $-19,280.00 | 10 | 13.68 |
| ATR Supertrend daily-primary 10max 3-initial entry guard | 253 | 60 | $235,057.00 | $-16,415.00 | $-17,352.00 | 10 | 13.55 |
| ATR Supertrend daily-primary 10max ladder 1/1/2/2/2 entry guard | 167 | 60 | $223,187.00 | $-17,120.00 | $-19,280.00 | 10 | 11.58 |
| ATR Supertrend daily weekly-flat 10max | 125 | 30 | $188,414.00 | $-16,415.00 | $-16,790.00 | 10 | 11.22 |
| ATR Supertrend daily weekly-flat 5max | 99 | 30 | $155,056.50 | $-11,907.50 | $-12,212.50 | 5 | 12.70 |
| Monthly ORB restricted scaleout3 | 417 | 81 | $105,154.00 | $-9,032.00 | $-12,058.00 | 3 | 8.72 |
| Monthly ORB overlap range breakout daily-ST retest x5 | 83 | 23 | $87,586.28 | $-17,995.04 | $-18,946.04 | 12 | 4.62 |

## Caveat

Artifact rows validate the execution book and MTM heat, not live-runtime signal generation. To reach the same confidence level as Yearly ORB, each candidate still needs a proper `StrategyPlugin` pass through `PaperBroker`.
