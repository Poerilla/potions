# EURUSD FBO runner@2R BE@TP25 — HTF entry filters (broker stress)

First-break opposite, close-SL, TP 0.25R/1R/2R, BE after TP25. Fee $7.00/unit.
Filter applies at the arming daily close (signal causal; fill next bar+):
- `ema100_1h`: entry direction must agree with last 1H close vs EMA100(1H)
- `atr80`: block entries when daily ATR14 rolling-500 percentile > 0.80

| Variant | Campaigns | WR | Net | Stress DD | Net/Stress |
|---|---:|---:|---:|---:|---:|
| 1/1/3 baseline (unfiltered) | 173 | 50.3% | $77,281 | $-74,027 | 1.04 |
| 1/1/3 ema100_1h | 167 | 49.1% | $62,454 | $-62,007 | 1.01 |
| 1/1/3 **atr80 only** | 146 | 52.1% | $91,898 | $-56,828 | **1.62** |
| 1/1/3 **ema100+atr80** | 138 | 50.7% | $69,015 | **$-40,425** | **1.71** |
| 1/2/3 baseline | 173 | 50.3% | $90,640 | $-88,758 | 1.02 |
| 1/2/3 ema100_1h | 167 | 47.9% | $72,274 | $-74,923 | 0.96 |
| 1/2/3 atr80 only | 146 | 50.7% | $105,827 | $-68,007 | 1.56 |
| 1/2/3 ema100+atr80 | 138 | 47.8% | $79,278 | $-48,236 | 1.64 |

## Findings

1. **The EMA100(1H) filter did NOT survive the in-engine rerun.** Counterfactual
   drop-from-fills said +$127k / −$47k; live gating gives +$62k / −$62k (~baseline).
   Canceling/delaying the entry stop changes which trades happen (different fill
   days, re-arms, freed monthly budget) — the counterfactual's dropped losers
   largely come back as different trades. Selection-bias caveat confirmed.
2. **The ATR≤80 regime filter is the real edge.** Alone: net UP (+$92k vs +$77k)
   and stress DOWN (−$57k vs −$74k), N/S 1.62. It skips panic-vol months where
   the fade gets run over.
3. **Combo** hits the lowest stress (−$40k, a 45% cut vs baseline) at roughly
   baseline net → best N/S 1.71, but the EMA leg mostly just costs net vs
   atr80-only.
4. Same ordering on **1/2/3** (sanity check passed: atr80 1.56, combo 1.64 vs 1.02).
5. Era check (1/1/3): atr80-only positive in 3 of 4 eras; 2015–20 still the weak
   era (−$25k) — the filter does not fix that regime, it trims 03-08/09-14 vol
   disasters.

## Recommendation

Promote **1/1/3 + atr80** (net up, stress down, simple, single knob) or
**1/1/3 + ema100+atr80** if minimizing stress is the priority.

Plugin support: `entry_filter_csv` (date,long_ok,short_ok) in
`live/strategies/monthly_orb_v2b_oco.py`. Filter CSVs under `filters/`.
Driver: `live/eurusd_monthly_orb_fbo_filtered_broker.py` (+ inline atr80-only run).
Counterfactual study: `../eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/stress_reduction_study/`.
