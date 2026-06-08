# v2b 09:45 Clean Break Ladder3 Runner

Three-contract variant of the 09:45 clean-break / RH-boundary-stop idea.

Rules:

- Opening range: 09:30, 09:35, and 09:40 five-minute candles.
- Trade only when the 09:45 candle is the first break and it breaks upward.
- Entry: `RH + 1 tick + 1 slip tick(s)`.
- If the 09:45 candle does not close above `RH`, close all 3 contracts at that close.
- 1 contract exits at 1R, 1 contract exits at 2R.
- Until 2R is hit, all remaining contracts use `RH` as the stop.
- Once only the runner remains after 2R, runner stop moves to 1R.
- Runner exits at 1R stop or EOD.

## Broker-Like StrategyPlugin Update

The ladder version now runs through `live/strategies/v2b_clean_break.py` and `live/v2b_clean_break_replays.py`. Report: `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`.

The broker-like pass removes same-breakout-candle target credit by waiting for the 09:45 candle to close cleanly before submitting TP1, TP2, and the boundary stop.

| Market | Trades | Units | Net | Closed DD | Intrabar Stress DD | Net / Stress | Win Rate | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 439 | 1,317 | $2,363.00 | -$3,012.50 | -$3,123.00 | 0.76 | 9.6% | 1.10 |
| NQ | 1,161 | 3,483 | $62,205.50 | -$26,495.00 | -$27,315.50 | 2.28 | 9.5% | 1.20 |

Read: the runner does add net versus the single boundary-stop version, but it adds exposure faster than edge. On MNQ it is weaker than the broad clean-break and weaker than the 09:45 RL-stop baseline on stress efficiency.

## Summary

| Market | Trades | Wins | Losses | Win Rate | TP1 Hits | TP2 Hits | Failed Clean | Boundary Stops | Runner 1R Stops | Runner EOD | Net | Max DD | PF | Avg Trade | Avg Win | Avg Loss | Largest Loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 435 | 53 | 382 | 12.2% | 53 | 28 | 196 | 205 | 14 | 20 | $4,943 | $-2,516 | 1.23 | $11 | $497 | $-56 | $-566 |
| NQ | 1186 | 141 | 1045 | 11.9% | 140 | 66 | 569 | 527 | 28 | 62 | $61,910 | $-22,995 | 1.19 | $52 | $2,695 | $-304 | $-5,595 |

## Output CSVs

- `mnq/mnq_v2b_clean_break_4th_candle_ladder3_runner.csv`
- `nq/nq_v2b_clean_break_4th_candle_ladder3_runner.csv`
