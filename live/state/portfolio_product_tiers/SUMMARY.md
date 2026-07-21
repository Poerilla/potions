# Portfolio product tiers (5% / 10% / 15% / 20%)

Hypothetical/backtested multi-product suite sharing one sleeve universe. Weights and profit-lock thresholds differ by tier. Not audited live performance.

## Context

- Inputs: [`../institutional_strategy_metrics/`](../institutional_strategy_metrics/SUMMARY.md)
- Prior single-product path: [`../target_10pct_portfolio/`](../target_10pct_portfolio/SUMMARY.md) (= Tier B)
- Precursors: [`orb-portfolio/`](../../../orb-portfolio/README.md), MNQ+MYM yearly blend

## Tier map

| Tier | Target | Haircut | Lock residual | Lock threshold | Design Σ | Full Σ |
|---|---:|---:|---:|---:|---:|---:|
| **Tier A · 5% target (low risk)** | 5% | 70% | 5% | 1.00× | 5.2% | 7.4% |
| **Tier B · 10% target (baseline)** | 10% | 70% | 10% | 1.00× | 11.7% | 16.7% |
| **Tier C · 15% target (medium-high)** | 15% | 70% | 15% | 1.25× | 14.9% | 21.3% |
| **Tier D · 20% target (high risk)** | 20% | 100% | 25% | 1.50× | 21.5% | 21.5% |

### Blurbs

- **A_5pct:** Trend/mild FX backbone; v2b ≤5% combined; tight profit-lock.
- **B_10pct:** Current product mix; medium risk; design contrib ≈11.7%.
- **C_15pct:** More v2b + USDJPY Monday OR; lock thresholds raised ~25%.
- **D_20pct:** Highest intraday weight; no design haircut; looser lock (more upside).

## Weights by tier

| Sleeve | Bucket | A 5% | B 10% | C 15% | D 20% |
|---|---|---:|---:|---:|---:|
| nq_v2b | high | 2% | 15% | 22% | 20% |
| mnq_v2b | high | 1% | 5% | 7% | 8% |
| ym_v2b | high | 1% | 5% | 6% | 7% |
| mym_v2b | medium | 1% | 4% | 4% | 5% |
| mnq_hourly | medium | 3% | 4% | 5% | 6% |
| usdjpy_mon_or | core_fx | 10% | 22% | 28% | 26% |
| audjpy_mon_or | mild | 8% | 6% | 3% | 3% |
| eurusd_fbo | mild | 14% | 8% | 4% | 3% |
| usdjpy_fbo | mild | 12% | 6% | 3% | 3% |
| eurusd_stpmc | mild | 10% | 5% | 2% | 2% |
| nq_yearly | trend | 14% | 8% | 6% | 7% |
| audjpy_yearly | trend | 12% | 6% | 5% | 5% |
| xau_yearly | trend | 12% | 6% | 5% | 5% |

## Realized backtest (compounded wealth, $300k)

### Preferred path — profit-lock 2010–2026

| Tier | CAGR | Max DD | +Years | Median year | Worst year | Best year |
|---|---:|---:|---:|---:|---:|---:|
| A_5pct | **11.2%** | -5.5% | 17/17 | 7.7% | 1.7% | 34.3% |
| B_10pct | **14.4%** | -8.8% | 17/17 | 14.1% | 0.3% | 42.0% |
| C_15pct | **18.4%** | -11.8% | 15/17 | 18.6% | -0.2% | 54.7% |
| D_20pct | **22.3%** | -11.4% | 17/17 | 19.3% | 0.5% | 75.9% |

### Uncapped static 2010–2026 (shows why locks matter)

| Tier | CAGR | Max DD | Median year | Best year |
|---|---:|---:|---:|---:|
| A_5pct | 12.2% | -5.4% | 8.5% | 40.8% |
| B_10pct | 20.2% | -8.8% | 15.0% | 89.0% |
| C_15pct | 25.6% | -11.8% | 18.7% | 123.8% |
| D_20pct | 25.7% | -11.4% | 19.3% | 122.1% |

## How to read this for allocators

- **Advertised target** is the design risk budget (weight × haircuted CAGR), not a guarantee.
- **Profit-lock** path is the product operating rule; static uncapped is diagnostic only.
- Tier A is the consistency engine; Tier D is high-octane managed futures with larger residual lock scale.
- Same sleeves and ops stack; only risk budgeting and lock thresholds change.

Generator: [`../../../scripts/portfolio_product_tiers.py`](../../../scripts/portfolio_product_tiers.py).

Per-tier folders: [`A_5pct/`](A_5pct/SUMMARY.md), [`B_10pct/`](B_10pct/SUMMARY.md), [`C_15pct/`](C_15pct/SUMMARY.md), [`D_20pct/`](D_20pct/SUMMARY.md).
