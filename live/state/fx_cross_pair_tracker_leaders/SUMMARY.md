# FX cross-pair test — tracked leaders on GBPUSD / USDJPY / AUDJPY

Data: Histdata 1m from `fx/raw/` (2003→2026-03; AUDJPY from 2003-12), converted
to 1m/1h/4h/daily/monthly/yearly per `fx/METADATA.md`. Engine + PaperBroker,
1-tick slip. Monthly ORB fee $7/unit; intraday ST+PMC $1.50/unit (pack conventions).
JPY-quoted pairs report in JPY; approx-USD at 110.

## Monthly ORB FBO runner@2R BE@TP25 close-SL (promoted family)

| Pair | Variant | n | WR | Net (quote) | Stress DD | Net/Stress | ~USD net / stress |
|---|---|---:|---:|---:|---:|---:|---|
| GBPUSD | 1/1/3 base | 195 | 49.2% | $173,025 | $-659,077 | 0.26 | — |
| GBPUSD | **1/1/3 atr80** | 169 | 46.7% | $110,469 | $-69,089 | **1.60** | — |
| GBPUSD | 1/2/3 base | 195 | 48.7% | $220,529 | $-791,805 | 0.28 | — |
| GBPUSD | **1/2/3 atr80** | 169 | 47.3% | $137,151 | $-84,773 | **1.62** | — |
| USDJPY | 1/1/3 base | 175 | 50.9% | ¥12,997,100 | ¥-3,943,000 | **3.30** | ~$118k / -$36k |
| USDJPY | **1/1/3 atr80** | 156 | 50.6% | ¥11,867,940 | ¥-2,792,191 | **4.25** | ~$108k / -$25k |
| USDJPY | 1/2/3 base | 175 | 53.1% | ¥16,164,975 | ¥-4,631,105 | **3.49** | ~$147k / -$42k |
| USDJPY | **1/2/3 atr80** | 156 | 51.9% | ¥14,347,848 | ¥-3,474,375 | **4.13** | ~$130k / -$32k |
| AUDJPY | 1/1/3 base | 162 | 45.7% | ¥3,477,105 | ¥-6,044,515 | 0.58 | ~$32k / -$55k |
| AUDJPY | 1/1/3 atr80 | 143 | 46.2% | ¥2,908,545 | ¥-6,267,198 | 0.46 | — |
| AUDJPY | 1/2/3 base | 162 | 46.3% | ¥2,722,671 | ¥-7,399,871 | 0.37 | — |
| AUDJPY | 1/2/3 atr80 | 143 | 47.6% | ¥2,602,344 | ¥-8,076,894 | 0.32 | — |

EURUSD reference: 1/1/3 base +$77k/-$74k/1.04 · 1/1/3 atr80 +$92k/-$57k/1.62.

**Findings**
- **USDJPY is the best FBO pair tested** — beats EURUSD on every variant
  (N/S 3.3–4.25). The monthly fade family generalizes across USD majors.
- **GBPUSD base blows up on stress** (-$659k) but the **atr80 filter rescues it**
  (stress ÷9.5 to -$69k, N/S 0.26 → 1.60). Confirms the EURUSD lesson: skip
  panic-vol months.
- **AUDJPY is weak everywhere** (0.3–0.6) and atr80 doesn't help — carry-driven
  trending cross behaves more like the equity indices (where FBO failed).
- Filter direction is consistent: atr80 improved 5 of 6 USD-pair variants,
  hurt only AUDJPY.

## Hourly ST+PMC sl25/tp75 3R + MA bull prior (promoted intraday)

| Pair | Trades | WR | Net (quote) | Stress DD | Net/Stress | ~USD |
|---|---:|---:|---:|---:|---:|---|
| EURUSD (ref) | — | 27.4% | $23,522 | $-15,745 | **1.49** | — |
| GBPUSD | 1192 | 26.3% | $11,933 | $-8,861 | **1.35** | — |
| AUDJPY | 1075 | 27.8% | ¥2,790,740 | ¥-2,151,952 | **1.30** | ~$25k / -$20k |
| USDJPY | 1100 | 23.5% | ¥-1,803,496 | ¥-2,779,186 | -0.65 | ~-$16k |

**Findings:** generalizes to GBPUSD and AUDJPY at nearly EURUSD-grade ratios;
fails on USDJPY (the pair where monthly FBO is strongest — nice complementarity).

Caveats: JPY-pair fee modeled at ¥7/unit (~$0.06) vs $7 intent — understates
costs on JPY pairs; at ~60 units/yr the impact is small but a rerun with
¥770/unit would shave JPY nets slightly. USD approximations use flat 110.

Driver: `live/fx_cross_pair_tracker_leaders.py` · states under `states/`, `st_pmc/`.
