# v2b 4th-Candle Clean Break With Boundary Stop

This variant only trades when the initial bullish breakout happens on **09:45 / 4th RTH candle**.

Rules:

- Opening range: 09:30, 09:35, and 09:40 five-minute candles.
- First post-range break only. If it is not the required candle or not bullish, skip.
- Buy stop: `RH + 1 tick + 1 slip tick(s)`.
- Breakout candle must close above `RH`; otherwise close at that candle close.
- After the breakout candle closes cleanly, stop moves immediately to `RH`.
- Any later trade back into the range exits at `RH`.
- Target remains `entry + 2 * opening_range`.
- Same-bar ambiguity after the clean close is boundary-stop first.

## Broker-Like StrategyPlugin Update

The 09:45 variants now run through `live/strategies/v2b_clean_break.py` and `live/v2b_clean_break_replays.py`. Report: `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`.

The broker-like version waits for the 09:45 candle to close cleanly before submitting the boundary stop and target, so same-breakout-candle target fills from this older detector are no longer credited.

| Market | Variant | Trades | Net | Closed DD | Intrabar Stress DD | Net / Stress | Win Rate | PF |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 09:45 RL-stop baseline | 436 | $5,110.50 | -$3,256.00 | -$3,280.50 | 1.56 | 28.9% | 1.20 |
| MNQ | 09:45 RH boundary stop | 439 | $1,553.50 | -$1,023.50 | -$1,053.50 | 1.47 | 8.2% | 1.19 |
| NQ | 09:45 RL-stop baseline | 1,157 | $85,804.50 | -$31,749.50 | -$32,059.50 | 2.68 | 28.0% | 1.25 |
| NQ | 09:45 RH boundary stop | 1,161 | $31,333.50 | -$9,194.50 | -$9,513.00 | 3.29 | 8.0% | 1.29 |

Read: the boundary stop still improves stress efficiency, especially on NQ, but the hit rate is very low and the MNQ net is too thin to outrank the broader clean-break or hardened OCO rows.

## Summary

| Market | Sessions | Trades | Targets | Boundary Stops | Failed Clean | EOD | Target Rate | Win Rate | Net | Max DD | PF | Avg Trade |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 1325 | 435 | 28 | 205 | 196 | 6 | 6.4% | 7.8% | $2,414 | $-874 | 1.34 | $6 |
| NQ | 4046 | 1186 | 66 | 527 | 569 | 24 | 5.6% | 7.6% | $31,235 | $-8,025 | 1.29 | $26 |

## Baseline Comparison

Compared with the broader clean-break baseline filtered to the same 09:45 first-break entries, the boundary stop improves drawdown but cuts away many winners:

| Market | Variant | Trades | Targets | Stops / Boundary Stops | Failed Clean | EOD | Net | Max DD | PF | Avg Trade |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 09:45 baseline, old RL stop | 435 | 74 | 104 | 196 | 61 | $6,211 | $-3,171 | 1.25 | $14 |
| MNQ | 09:45 RH boundary stop | 435 | 28 | 205 | 196 | 6 | $2,414 | $-874 | 1.34 | $6 |
| NQ | 09:45 baseline, old RL stop | 1186 | 178 | 260 | 569 | 179 | $88,275 | $-31,625 | 1.26 | $74 |
| NQ | 09:45 RH boundary stop | 1186 | 66 | 527 | 569 | 24 | $31,235 | $-8,025 | 1.29 | $26 |

Interpretation: moving the stop to `RH` immediately after the 09:45 candle closes does make the system much more capital-efficient, but it also converts a large number of eventual winners into tiny boundary-stop exits. The remaining edge is positive, but much thinner.

If “4th candle” means break #4 after the OR, i.e. 10:00 ET instead of the 09:45 candle, the sample becomes very small: MNQ 40 trades / 1 target / $206 net; NQ 142 trades / 7 targets / $5,965 net.

## Output CSVs

- `mnq/mnq_v2b_clean_break_4th_candle_boundary_stop.csv`
- `nq/nq_v2b_clean_break_4th_candle_boundary_stop.csv`

## MNQ Outcome Charts

- [Winners](charts/winners/INDEX.md)
- [Losers](charts/losers/INDEX.md)
