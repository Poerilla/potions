# touch_st_align — broker gate

## Rules
1. Watch program structure key (buy→bull LL / sell→bear HH)
2. Require **touch + trade-through**
3. Wait for **1m ST flip** aligned with program bias
4. **Market** entry on flip; initial SL = newly formed ST trail
5. At **+25**: scale 5, tighten SL to **±12**
6. Then 5 @ +50, 5 @ +200; favourable ST→BE (same shape as scale_run)

## Results

| | Analytic | PaperBroker |
|--|--:|--:|
| Trades | 1215 | 1391 |
| Net | +$1.37M | **−$1.25M** |
| PF | 1.30 | **0.84** |
| Win% | 57.7 | 45.1 camp / 31.5 unit |
| hold≤1 share | — | **~1%** |

**FAIL** (TRL-2026-00084). Entry timing largely removes next-bar death; the managed
ladder / adverse ST / risk stops still lose under broker fills.

Charts: [`trade_charts/`](trade_charts/) — 100 winners + 100 losers (1m, OR, ST, structure).
