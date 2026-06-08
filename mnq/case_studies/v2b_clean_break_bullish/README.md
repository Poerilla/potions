# v2b Clean Break Bullish Study

This revisits v2b as a **bullish-only, first-break-only** clean-break detector on 5-minute RTH bars.

Rules used in this first pass:

- Opening range: 09:30, 09:35, and 09:40 five-minute candles.
- First post-range break only. If the first break is down, the day is skipped.
- Buy stop: `RH + 1 tick + 1 slip tick(s)`.
- Clean requirement: the breakout candle must close above `RH`; otherwise the trade closes at that 5-minute close.
- Target: `entry + 2 * opening_range`.
- Stop: existing v2b-style opposite OR boundary, `RL`.
- After the breakout candle, ambiguous same-bar stop/target ordering is stop-first.

This is a 5-minute research pass. The exact order of high/low events inside a five-minute candle is not proven here.

## Broker-Like StrategyPlugin Update

The clean-break family now has a `StrategyPlugin` replay through `Engine + PaperBroker`: `live/strategies/v2b_clean_break.py`, runner `live/v2b_clean_break_replays.py`, report `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`.

Main realism change: the buy stop can fill during the breakout 5-minute candle, but the clean-close test is only known after that candle completes. Protective stops/targets are submitted after that close and only become active from the next 5-minute bar. Same-breakout-candle targets from the old detector are therefore not credited.

| Market | Trades | Net | Closed DD | Intrabar Stress DD | Net / Stress | Win Rate | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 675 | $9,498.50 | -$1,886.50 | -$1,950.00 | 4.87 | 28.9% | 1.25 |
| NQ | 2,039 | $112,026.50 | -$19,025.00 | -$19,115.00 | 5.86 | 28.2% | 1.20 |

Read: the broad bullish clean-break idea survives the broker-like pass, but with a haircut versus the original detector row because same-candle target credit is removed and opposite-side sweeps are flattened as ambiguous.

## Summary

| Market | Sessions | Initial Up | Failed Clean | Clean Breaks | Targets | Stops | EOD | Target Rate / Up | Target Rate / Clean | Net | Max DD | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 1325 | 677 | 311 | 366 | 108 | 150 | 108 | 16.0% | 29.5% | $11,066 | $-1,799 | 1.30 |
| NQ | 4046 | 2061 | 957 | 1104 | 288 | 459 | 357 | 14.0% | 26.1% | $119,370 | $-18,010 | 1.21 |

## Winner Clean-Break Timing

### MNQ

| Break candle # after OR | Time ET | Target winners |
|---:|---:|---:|
| 1 | 09:45 | 74 |
| 2 | 09:50 | 17 |
| 3 | 09:55 | 8 |
| 4 | 10:00 | 3 |
| 5 | 10:05 | 2 |
| 8 | 10:20 | 2 |
| 7 | 10:15 | 1 |
| 9 | 10:25 | 1 |

### NQ

| Break candle # after OR | Time ET | Target winners |
|---:|---:|---:|
| 1 | 09:45 | 178 |
| 2 | 09:50 | 54 |
| 3 | 09:55 | 25 |
| 4 | 10:00 | 14 |
| 5 | 10:05 | 6 |
| 7 | 10:15 | 4 |
| 8 | 10:20 | 4 |
| 9 | 10:25 | 2 |
| 6 | 10:10 | 1 |

## Output CSVs

- `mnq/mnq_v2b_clean_break_bullish.csv`
- `nq/nq_v2b_clean_break_bullish.csv`

## Winner Chart Samples

- [MNQ 50 winner sample](charts/mnq_winners/INDEX.md)
- [NQ 50 winner sample](charts/nq_winners/INDEX.md)
