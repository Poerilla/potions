# V2B Intraday StrategyPlugin Replay

This hardens the v2b family into a true intraday `StrategyPlugin` path. The old `$83k / -$3.1k` row is retained as a research scanner reference only: it scans Long first across the whole day and can therefore choose a later Long over an earlier Short. The live-orderable rows below use actual resting order modes.

| Mode | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| strict_long_then_short | 12 | 6 | $953.50 | $-1,004.00 | $-1,030.00 | 2 | 0.93 | 66.7% | 1.86 |
| oco_then_reverse | 14 | 7 | $808.00 | $-1,120.50 | $-1,146.50 | 2 | 0.70 | 57.1% | 1.73 |

## Live Read

- `oco_then_reverse` is closest to a normal TV/Tradovate harness: both breakout stops are live after the 09:30-09:45 OR, first fill wins, and the opposite side may arm after that leg exits.
- `strict_long_then_short` is the literal executable version of the old wording: short is allowed only after a filled long exits. If long never fills, no short is taken.
- The plugin submits protective exits from `on_fill`; TP1 cancels/rebuilds TP2 behind the runner stop so same-bar runner-stop-vs-TP2 ambiguity stays pessimistic.
- Fees are applied in the audit at `$1.50` per closed MNQ unit, matching the research run.
