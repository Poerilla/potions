# Monthly ORB Overlap Daily-ST Retest x5 Broker-Like Replay

This promotes the research `breakout_only_2active_daily_st_retest5` idea into a 4h `StrategyPlugin` replay.

Important implementation hardening:

- Primary entries are actual resting buy-stop orders at the combined overlap high.
- Orders become active only after the 4h bar that created/updated the signal has closed.
- Confirmed daily Supertrend is used as the long filter.
- The retest add is an actual 5-contract buy-limit at the confirmed daily Supertrend stop, not a same-bar hindsight fill.
- Retest add exits at the parent runner target or on a 4h close below the current confirmed daily Supertrend stop.
- Daily close invalidation closes primary and retest units when price closes 25% back into the combined range.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ Monthly ORB overlap daily-ST retest x5 | NQ | 277 | 73 | $787,810.65 | -$100,695.00 | -$108,654.57 | 12 | 7.25 |
| 2 | YM Monthly ORB overlap daily-ST retest x5 | YM | 287 | 75 | $247,381.98 | -$53,380.00 | -$54,030.00 | 10 | 4.58 |
| 3 | ES Monthly ORB overlap daily-ST retest x5 | ES | 316 | 82 | $322,846.81 | -$76,019.47 | -$76,881.97 | 12 | 4.20 |
| 4 | MNQ Monthly ORB overlap daily-ST retest x5 | MNQ | 119 | 31 | $73,523.42 | -$17,397.20 | -$18,348.20 | 12 | 4.01 |
| 5 | MYM Monthly ORB overlap daily-ST retest x5 | MYM | 118 | 30 | $14,043.10 | -$4,795.10 | -$5,053.10 | 8 | 2.78 |
| 6 | MES Monthly ORB overlap daily-ST retest x5 | MES | 94 | 24 | $8,744.23 | -$7,745.55 | -$7,828.05 | 8 | 1.12 |

Research reference for MNQ close-fill branch was about `$87,586 / -$18,175` pess. intrabar stress. Expect the broker-like replay to be stricter because retest limits must be live before the fill bar.
