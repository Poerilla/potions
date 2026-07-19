# $250k book — pause after a green month (FBO 1/1/3 ema100+atr80)

Rule: if a calendar month closes green, take **no new campaigns the next month**;
resume the month after (one-month cooldown). Counterfactual on broker fills.

| Metric | Always-on | Pause-after-green |
|---|---:|---:|
| Net P&L (22.9y) | $64,184 | **$94,869** |
| CAGR | 1.0% | **1.41%** |
| Sharpe | 0.21 | **0.31** |
| Ann. vol | 4.39% | 3.92% |
| Max DD (close) | -11.55% | -12.34% |
| Stress DD | -$40,950 (-12.7%) | -$37,573 (-12.6%) |
| Exposure | 9.8% | 7.8% |
| Campaigns / WR / PF | 138 / 50.7% / 1.26 | **109 / 54.1% / 1.54** |
| Positive years | 50% | 58% |

52 months paused; the 29 skipped campaigns summed to **-$30.7k** — post-green months
were net losers (mean-reversion in monthly P&L).

Caveats: one specific cooldown rule tested (not swept), so treat as suggestive;
skipped-month campaigns were removed whole; monthly P&L autocorrelation may be
sample-specific. A broker-honest version would gate arming by prior-month P&L
in the plugin (trivial to add via the same entry-filter mechanism).

Chart: `equity_compare.png`. Tables: `yearly_returns.csv`, `monthly_returns_pct.csv`.
