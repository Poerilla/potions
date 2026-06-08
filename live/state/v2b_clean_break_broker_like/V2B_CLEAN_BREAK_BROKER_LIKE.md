# V2B Clean-Break Broker-Like Replays

These rows harden the clean-break research scripts into `StrategyPlugin` replays through `Engine + PaperBroker` using completed 5-minute RTH bars. Entry stops can fill during the breakout candle, but the clean-close requirement is evaluated only after that 5-minute candle closes. Protective exits become active from the next 5-minute bar.

Fees: `$1.50` per closed unit. Entry offset: `OR high + 2 ticks`, matching the old `one tick + one slippage tick` research scripts.

| Rank | Market | Variant | Sessions | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | MNQ | Bullish clean break, 2R target, RL stop | 1325 | 675 | 675 | $8,877.50 | $-1,952.00 | $-2,015.50 | 1 | 4.40 | 28.9% | 1.23 |
| 2 | NQ | Bullish clean break, 2R target, RL stop | 4046 | 2039 | 2039 | $93,096.50 | $-24,444.50 | $-24,534.50 | 1 | 3.79 | 28.2% | 1.16 |
| 3 | NQ | 09:45 clean break, 2R target, RL stop baseline | 4046 | 1157 | 1157 | $75,124.50 | $-32,264.50 | $-32,579.50 | 1 | 2.31 | 28.0% | 1.22 |
| 4 | NQ | 09:45 clean break, 2R target, boundary stop | 4046 | 1161 | 1161 | $20,053.50 | $-9,614.50 | $-9,928.00 | 1 | 2.02 | 8.0% | 1.17 |
| 5 | MNQ | 09:45 clean break, 2R target, RL stop baseline | 1325 | 436 | 436 | $4,711.50 | $-3,307.50 | $-3,332.50 | 1 | 1.41 | 28.9% | 1.18 |
| 6 | MNQ | 09:45 clean break, 2R target, boundary stop | 1325 | 439 | 439 | $1,128.50 | $-1,067.50 | $-1,133.00 | 1 | 1.00 | 8.2% | 1.13 |
| 7 | NQ | 09:45 clean break, 3-lot ladder runner | 4046 | 1161 | 3483 | $28,405.50 | $-28,070.00 | $-28,880.00 | 3 | 0.98 | 9.5% | 1.08 |
| 8 | MNQ | 09:45 clean break, 3-lot ladder runner | 1325 | 439 | 1317 | $1,086.50 | $-3,181.00 | $-3,473.50 | 3 | 0.31 | 9.6% | 1.04 |

## Realism Notes

- The old clean-break scripts could credit some same-breakout-candle target hits after the entry. This broker-like replay does not: exits are only submitted after the candle closes cleanly.
- If the breakout candle also sweeps the opposite side of the range, the plugin flattens at that candle close as an ambiguous break instead of accepting a clean long.
- This is still 5-minute-bar realism, not tick replay. Intrabar stress uses each 5-minute bar's adverse extreme.
- `fourth_rl_2r` is included because it appears as the historical baseline comparison for the 09:45 study, even though it did not have a standalone plugin before this pass.
