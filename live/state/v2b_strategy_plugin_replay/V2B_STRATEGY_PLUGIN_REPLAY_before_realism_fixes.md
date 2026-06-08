# V2B Intraday StrategyPlugin Replay

This hardens the v2b family into a true intraday `StrategyPlugin` path. The old `$83k / -$3.1k` row is retained as a research scanner reference only: it scans Long first across the whole day and can therefore choose a later Long over an earlier Short. The live-orderable rows below use actual resting order modes.

| Mode | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Net / Stress | Win % | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| oco_then_reverse | 2806 | 1406 | $34,444.50 | $-5,841.50 | $-5,869.50 | 2 | 5.87 | 46.2% | 1.19 |
| strict_long_then_short | 2102 | 1052 | $18,926.50 | $-6,153.00 | $-6,163.00 | 2 | 3.07 | 46.1% | 1.14 |

## Live Read

- `oco_then_reverse` is closest to a normal TV/Tradovate harness: both breakout stops are live after the 09:30-09:45 OR, first fill wins, and the opposite side may arm after that leg exits.
- `strict_long_then_short` is the literal executable version of the old wording: short is allowed only after a filled long exits. If long never fills, no short is taken.
- The plugin submits protective exits from `on_fill`; TP1 cancels/rebuilds TP2 behind the runner stop so same-bar runner-stop-vs-TP2 ambiguity stays pessimistic.
- Fees are applied in the audit at `$1.50` per closed MNQ unit, matching the research run.

## Charts

- OCO then reverse chart pack: [`charts/oco_then_reverse/INDEX.md`](charts/oco_then_reverse/INDEX.md)
- Builder: [`../../build_v2b_strategy_charts.py`](../../build_v2b_strategy_charts.py)

## Cross-Market Pass

The same OCO-then-reverse plugin was replayed on NQ, YM, MYM, ES, and MES from the common start date `2021-03-04`. NQ was the strongest row: **$389,026.50 net / -$58,840.00 intrabar stress DD / 6.61 Net-Stress**. Full table: [`../v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md`](../v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md). NQ charts: [`../v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md`](../v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md).
