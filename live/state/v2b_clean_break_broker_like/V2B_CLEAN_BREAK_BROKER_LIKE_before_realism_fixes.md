# V2B Clean-Break Broker-Like Replays

These rows harden the clean-break research scripts into `StrategyPlugin` replays through `Engine + PaperBroker` using completed 5-minute RTH bars. Entry stops can fill during the breakout candle, but the clean-close requirement is evaluated only after that 5-minute candle closes. Protective exits become active from the next 5-minute bar.

Fees: `$1.50` per closed unit. Entry offset: `OR high + 2 ticks`, matching the old `one tick + one slippage tick` research scripts.

| Rank | Market | Variant | Sessions | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | Bullish clean break, 2R target, RL stop | 4046 | 2039 | 2039 | $112,026.50 | $-19,025.00 | $-19,115.00 | 1 | 5.86 | 28.2% | 1.20 |
| 2 | MNQ | Bullish clean break, 2R target, RL stop | 1325 | 675 | 675 | $9,498.50 | $-1,886.50 | $-1,950.00 | 1 | 4.87 | 28.9% | 1.25 |
| 3 | NQ | 09:45 clean break, 2R target, boundary stop | 4046 | 1161 | 1161 | $31,333.50 | $-9,194.50 | $-9,513.00 | 1 | 3.29 | 8.0% | 1.29 |
| 4 | NQ | 09:45 clean break, 2R target, RL stop baseline | 4046 | 1157 | 1157 | $85,804.50 | $-31,749.50 | $-32,059.50 | 1 | 2.68 | 28.0% | 1.25 |
| 5 | NQ | 09:45 clean break, 3-lot ladder runner | 4046 | 1161 | 3483 | $62,205.50 | $-26,495.00 | $-27,315.50 | 3 | 2.28 | 9.5% | 1.20 |
| 6 | MNQ | 09:45 clean break, 2R target, RL stop baseline | 1325 | 436 | 436 | $5,110.50 | $-3,256.00 | $-3,280.50 | 1 | 1.56 | 28.9% | 1.20 |
| 7 | MNQ | 09:45 clean break, 2R target, boundary stop | 1325 | 439 | 439 | $1,553.50 | $-1,023.50 | $-1,053.50 | 1 | 1.47 | 8.2% | 1.19 |
| 8 | MNQ | 09:45 clean break, 3-lot ladder runner | 1325 | 439 | 1317 | $2,363.00 | $-3,012.50 | $-3,123.00 | 3 | 0.76 | 9.6% | 1.10 |

## Realism Notes

- The old clean-break scripts could credit some same-breakout-candle target hits after the entry. This broker-like replay does not: exits are only submitted after the candle closes cleanly.
- If the breakout candle also sweeps the opposite side of the range, the plugin flattens at that candle close as an ambiguous break instead of accepting a clean long.
- This is still 5-minute-bar realism, not tick replay. Intrabar stress uses each 5-minute bar's adverse extreme.
- `fourth_rl_2r` is included because it appears as the historical baseline comparison for the 09:45 study, even though it did not have a standalone plugin before this pass.
