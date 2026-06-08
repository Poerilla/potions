# Cross-Market v2b + ST/PMC Regime Weighting Research

All rows use each market's `S_1_1_3` v2b unit tape so the original MNQ plan's TP1/TP2/runner weighting scenarios remain comparable. ST+PMC uses each market's best available same-market candidate; YM uses the standalone YM variants run because it is not present in the cross-market best-by-market folder.

| Market | Base Net | Base Stress | Base Net/Stress | Prior-Opposed Trades | Prior-Opposed Net | Prior-Opposed PF | Prior-Opposed Net/Stress | Best Weighted Row | Best Weighted Net | Best Weighted Stress | Best Weighted Net/Stress |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| NQ | $867,355.00 | $-100,085.00 | 8.67 | 184 | $616,085.00 | 2.35 | 11.25 | `C_weight_not_aligned_2_1_3` | $1,011,896.00 | $-118,356.50 | 8.55 |
| ES | $-54,265.50 | $-269,726.50 | -0.20 | 35 | $39,275.00 | 1.78 | 1.35 | `C_weight_not_aligned_2_1_3` | $-63,808.50 | $-325,462.50 | -0.20 |
| MES | $-3,916.00 | $-17,843.50 | -0.22 | 64 | $3,395.00 | 1.32 | 0.83 | `B_hard_filter_not_aligned_1_1_3` | $-2,744.50 | $-16,098.25 | -0.17 |
| YM | $37,689.75 | $-204,425.25 | 0.18 | 120 | $36,893.75 | 1.24 | 0.93 | `D_weight_not_aligned_2_2_3` | $56,925.25 | $-277,595.75 | 0.21 |
| MYM | $-5,027.66 | $-24,343.03 | -0.21 | 208 | $9,632.24 | 1.35 | 2.88 | `C_weight_not_aligned_2_1_3` | $-5,999.78 | $-28,160.57 | -0.21 |

## Files

- `cross_market_readout.csv`
- `cross_market_scenario_matrix.csv`
- `cross_market_regime_decomposition.csv`

Per-market reports:

- `NQ`: [`nq/INDEX.md`](nq/INDEX.md)
- `ES`: [`es/INDEX.md`](es/INDEX.md)
- `MES`: [`mes/INDEX.md`](mes/INDEX.md)
- `YM`: [`ym/INDEX.md`](ym/INDEX.md)
- `MYM`: [`mym/INDEX.md`](mym/INDEX.md)