# MNQ Prior-Opposed ST+PMC v2b Execution Scrutiny

Rules are frozen. This audit looks for timing, causality, latency, and live-readiness problems; it does not optimize the strategy.

| Campaigns | Net | Win % | PF | Causal violations | Bar-safe | Ambiguous <=1m | Pre-arm touch | Later level retest | Trigger-only later touch | No later 1m touch | Tick manifest |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 353 | $113547.50 | 68.56 | 2.615 | 0 | 142 | 44 | 167 | 147 | 63 | 1 | 265 |

## Read

- Causality check passed at the fill-book level: every campaign found a prior opposite ST+PMC entry.
- Latency is not fully answered by 1m bars: 44 campaigns are same-minute ambiguous and 167 show the breakout level touched before the v2b gate/order was active.
- Coarse retest estimate: among the 211 not-bar-safe campaigns, 147 later span the entry level again on 1m bars, 63 later touch only the trigger side, and 1 show no later 1m touch before exit.
- This market is a strict StrategyPlugin delayed-arming replay.

## Files

- `historical_timing_report.csv`
- `latency_summary.csv`
- `delay_sensitivity_summary.csv`
- `retest_summary.csv`
- `tick_replay_manifest.csv`
