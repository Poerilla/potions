# Monthly ORB Overlap Daily-ST Retest x5 Broker-Like Replay

This promotes the research `breakout_only_2active_daily_st_retest5` idea into a 4h `StrategyPlugin` replay.

Realism knobs (2026-05-20 re-baseline): `slippage_ticks=1`, `fee_per_unit=$1.50`, stop gap-through enabled.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ Monthly ORB overlap daily-ST retest x5 | NQ | 277 | 73 | $549,975.70 | $-118,019.57 | $-127,454.57 | 12 | 4.32 |
| 2 | MNQ Monthly ORB overlap daily-ST retest x5 | MNQ | 119 | 31 | $60,325.40 | $-19,477.20 | $-20,428.20 | 12 | 2.95 |
| 3 | MYM Monthly ORB overlap daily-ST retest x5 | MYM | 118 | 30 | $9,812.65 | $-5,066.60 | $-5,324.60 | 8 | 1.84 |
| 4 | ES Monthly ORB overlap daily-ST retest x5 | ES | 316 | 82 | $135,734.40 | $-100,652.97 | $-101,515.47 | 12 | 1.34 |
| 5 | YM Monthly ORB overlap daily-ST retest x5 | YM | 193 | 51 | $15,090.15 | $-43,010.47 | $-46,115.47 | 10 | 0.33 |
| 6 | MES Monthly ORB overlap daily-ST retest x5 | MES | 94 | 24 | $2,612.94 | $-10,261.55 | $-10,344.05 | 8 | 0.25 |

Pre-fix snapshot preserved as `SUMMARY_before_realism_fixes.md` / `summary_before_realism_fixes.csv`.