# WO gap reversal — rule variant comparison

Full history from **2010-06-06** · exit **2ct +50 / runner 300** · SL **50 pts**.
Baseline matches the chart study except where a variant overrides one rule.

### Baseline rules (unchanged across variants unless noted)
- Pre-gap: ≥1 prior 1h bar fully O+C on exit side of WO
- Gap candle: ≥55% of O–C on exit side crossing WO
- Entry: limit @ WO from next bar; 6-bar fill window
- Post-gap swing filter: skip if 3-bar swing before retest (unless gap in swing)
- Max **2** trades/week; stop new trades after +50 / target win
- One gap signal per direction per week

## Both sides

| Variant | Trades | Net pts | Δ net vs base | Win% | PF | Avg/trade | Max DD | Max loss streak | Δ trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline (55% gap · swing filter · 2 trades/wk) | 494 | +7861.5 | +0.0 | 57.3 | 1.46 | +15.9 | -1202 | 6 | +0 |
| 1 — no swing filter before WO retest | 494 | +7861.5 | +0.0 | 57.3 | 1.46 | +15.9 | -1202 | 6 | +0 |
| 2a — 45% gap candle | 509 | +7818.8 | -42.8 | 56.2 | 1.44 | +15.4 | -1100 | 7 | +15 |
| 2b — 50% gap candle | 509 | +7818.8 | -42.8 | 56.2 | 1.44 | +15.4 | -1100 | 7 | +15 |
| 3 — max 3 trades/week | 494 | +7861.5 | +0.0 | 57.3 | 1.46 | +15.9 | -1202 | 6 | +0 |
| 4 — unlimited trades/week | 540 | +5007.5 | -2854.0 | 54.1 | 1.24 | +9.3 | -1402 | 7 | +46 |
| 5 — RTH-only entries (09:30–16:00) | 282 | +3194.2 | -4667.2 | 55.3 | 1.32 | +11.3 | -1481 | 12 | -212 |

- **1 — no swing filter before WO retest**: net +0.0 pts vs baseline, +0 trades, max DD +0 pts.
- **2a — 45% gap candle**: net -42.8 pts vs baseline, +15 trades, max DD +102 pts.
- **2b — 50% gap candle**: net -42.8 pts vs baseline, +15 trades, max DD +102 pts.
- **3 — max 3 trades/week**: net +0.0 pts vs baseline, +0 trades, max DD +0 pts.
- **4 — unlimited trades/week**: net -2854.0 pts vs baseline, +46 trades, max DD -200 pts.
- **5 — RTH-only entries (09:30–16:00)**: net -4667.2 pts vs baseline, -212 trades, max DD -279 pts.

## Short only

| Variant | Trades | Net pts | Δ net vs base | Win% | PF | Avg/trade | Max DD | Max loss streak | Δ trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline (55% gap · swing filter · 2 trades/wk) | 295 | +3282.8 | +0.0 | 53.6 | 1.30 | +11.1 | -2155 | 6 | +0 |
| 1 — no swing filter before WO retest | 295 | +3282.8 | +0.0 | 53.6 | 1.30 | +11.1 | -2155 | 6 | +0 |
| 2a — 45% gap candle | 306 | +3297.5 | +14.8 | 53.6 | 1.29 | +10.8 | -1917 | 6 | +11 |
| 2b — 50% gap candle | 306 | +3297.5 | +14.8 | 53.6 | 1.29 | +10.8 | -1917 | 6 | +11 |
| 3 — max 3 trades/week | 295 | +3282.8 | +0.0 | 53.6 | 1.30 | +11.1 | -2155 | 6 | +0 |
| 4 — unlimited trades/week | 295 | +3282.8 | +0.0 | 53.6 | 1.30 | +11.1 | -2155 | 6 | +0 |
| 5 — RTH-only entries (09:30–16:00) | 166 | +2738.0 | -544.8 | 56.6 | 1.49 | +16.5 | -961 | 10 | -129 |

- **1 — no swing filter before WO retest**: net +0.0 pts vs baseline, +0 trades, max DD +0 pts.
- **2a — 45% gap candle**: net +14.8 pts vs baseline, +11 trades, max DD +238 pts.
- **2b — 50% gap candle**: net +14.8 pts vs baseline, +11 trades, max DD +238 pts.
- **3 — max 3 trades/week**: net +0.0 pts vs baseline, +0 trades, max DD +0 pts.
- **4 — unlimited trades/week**: net +0.0 pts vs baseline, +0 trades, max DD +0 pts.
- **5 — RTH-only entries (09:30–16:00)**: net -544.8 pts vs baseline, -129 trades, max DD +1194 pts.
