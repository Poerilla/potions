# V2B Clean-Break Broker-Like Replays

These rows harden the clean-break research scripts into `StrategyPlugin` replays through `Engine + PaperBroker` using completed 5-minute RTH bars. Entry stops can fill during the breakout candle, but the clean-close requirement is evaluated only after that 5-minute candle closes. Protective exits become active from the next 5-minute bar.

Fees: `$1.50` per closed unit. Entry offset: `OR high + 2 ticks`, matching the old `one tick + one slippage tick` research scripts.

| Rank | Market | Variant | Sessions | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | MNQ | 09:45 clean break, 2R target, boundary stop | 25 | 10 | 10 | $186.50 | $-196.00 | $-269.00 | 1 | 0.69 | 20.0% | 1.90 |
| 2 | MNQ | Bullish clean break, 2R target, RL stop | 25 | 15 | 15 | $371.00 | $-559.00 | $-567.50 | 1 | 0.65 | 40.0% | 1.39 |

## Realism Notes

- The old clean-break scripts could credit some same-breakout-candle target hits after the entry. This broker-like replay does not: exits are only submitted after the candle closes cleanly.
- If the breakout candle also sweeps the opposite side of the range, the plugin flattens at that candle close as an ambiguous break instead of accepting a clean long.
- This is still 5-minute-bar realism, not tick replay. Intrabar stress uses each 5-minute bar's adverse extreme.
- `fourth_rl_2r` is included because it appears as the historical baseline comparison for the 09:45 study, even though it did not have a standalone plugin before this pass.
