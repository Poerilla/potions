# TOP3 equity curves — Clean Break ×10

Comparison-only scale: NAS100 Clean Break research tape ×10 (not live demo size).

## Sleeve board (×10 on Clean Break)

| Sleeve | Net | Stress | N/S | Scale |
|---|---:|---:|---:|---:|
| USDJPY Asia Range | $178141.92 | $-24627.15 | 7.23 | 1× |
| USDJPY Monday OR | $293270.36 | $-27726.13 | 10.58 | 1× |
| NAS100 Clean Break ×10 | $122529.50 | $-19658.50 | 6.23 | 10× |

## Combined (CB×10)

| Combined net | $593941.78 |
| Joint MTM stress | $-37866.37 |
| **Combined N/S (joint)** | **15.69** |
| Additive stress | $-72011.77 |
| Combined N/S (additive) | 8.25 |
| Diversification ratio | 1.90× |
| Mean pairwise daily PnL corr | -0.01 |
| Common start (all sleeves) | 2016-11-15 |
| Common-window net / joint N/S / add N/S | $382091.61 / 10.09 / 5.31 |

## Diversification read

- **Significant diversification**: joint N/S 15.69 vs additive 8.25 (ratio 1.90×). Median 2y rolling div-ratio 1.69×; median rolling mean corr 0.01.
- Clean Break ×10 is now ~21% of combined net (was ~3% at 1×), so index RTH heat actually moves the joint DD.

- Asia + Monday OR remain both USDJPY — clock diversification helps, but FX risk is related.
- Charts: `equity_curves_cb10x/`

## Artifacts

- `equity_separate_sleeves_cb10x.png`
- `equity_asia_range_cb10x.png` / `equity_monday_or_cb10x.png` / `equity_clean_break_cb10x.png`
- `equity_combined_cb10x.png`
- `diversification_evolution_cb10x.png`
- `diversification_expanding_common_cb10x.png`
- `drawdown_joint_vs_sum_cb10x.png`
