# $250k book — FBO 1/1/3 ema100_1h + atr80 (broker fills)

Position size fixed at the promoted 5 units (=$500k notional max, **2:1 max leverage** on $250k).
Equity marked daily at close; stress uses intrabar worst mark.

| Metric | Value |
|---|---:|
| Net P&L (22.9y) | $64,184 |
| Total return | 25.7% |
| **CAGR** | **1.0%** |
| Ann. vol | 4.39% |
| **Sharpe (daily, ann.)** | **0.21** |
| Sortino | 0.1 |
| Max DD (close) | -11.55% |
| Stress DD (intrabar) | $-40,950 (-12.67%) |
| Calmar | 0.09 |
| Exposure (days in mkt) | 9.8% |
| Campaigns / WR / PF | 138 / 50.7% / 1.26 |
| Best / worst month | +7.03% / -5.69% |
| Positive months / years | 21.8% / 50.0% |

Tables: `yearly_returns.csv`, `monthly_returns_pct.csv`, `equity_daily.csv`. Chart: `equity_250k.png`.

## Capacity vs quality (institutional grade?)

**Capacity: yes.** EURUSD spot turns over >$1T/day; entries are stop orders at
monthly OR boundaries on daily bars, ~14 fills/yr. This size ($0.5M notional) is
invisible; it would absorb 100–1000x with negligible slippage.

**Quality at this sizing: no.** CAGR ~1%, Sharpe ~0.2, exposure ~10%. As a
standalone $250k product it is not institutional grade — returns are too small
relative to capital because sizing is fixed at 5 lots regardless of equity.
It is an **overlay/sleeve**: leverage or vol-targeting scales return and risk
together (Sharpe stays ~0.2). e.g. 10x (50 lots, 20:1) ≈ ~10%/yr with ~±44%
vol-scaled stress — Sharpe unchanged. The binding constraint is the Sharpe,
not the market impact.
