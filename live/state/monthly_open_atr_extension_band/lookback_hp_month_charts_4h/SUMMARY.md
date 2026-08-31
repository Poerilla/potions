# NQ lookback HP 4h charts — liquidity-run overlay

First **2 full NY trading days**: largest |move| from month open = run on liquidity.
Box = `(t_open, t_liq, p_open, p_liq)`. Trade direction = opposite side of the run.

## Selection

Charts: **118** (OR of causal HP predictors).

## Liquidity-run profile (n=118)

| Metric | Value |
|---|---:|
| Liq run UP / DOWN | 69 / 49 |
| Avg / median liq extension (pts) | 194.1 / 132.4 |
| **Hit month open** after liq swing | **101 / 118 (85.6%)** |
| **Trade-dir ext > past-liq ext** | **55 / 118 (46.6%)** |
| Avg trade-dir extension (pts) | 385.6 |
| Avg past-liq extension (pts) | 389.3 |

### Joint

| Cohort | N |
|---|---:|
| Reclaim open **and** trade-dir wins | 55 |
| Reclaim open but past-liq wins | 46 |
| No reclaim, trade-dir wins | 0 |
| No reclaim, past-liq wins | 17 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/lookback_hp_month_charts_4h`
