# NAS100 v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay on MT5 NAS100 1m
(`fx/raw/NAS100_1m_data.csv` → `fx/nas100_1m.csv`, clocks `Europe/Athens` → NY).

Config matched to NQ Databento prior-opposed: `S_1_1_3`, ST+PMC `sl25_tp75_3r`
**index points**, fee `$1.50`/unit, slip 1 tick, start **2021-03-04**.
Point value `$1`/pt (NQ is `$20`/pt).

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 310 | 1550 | $923.00 | $-7810.25 | $-7862.25 | 47.10 | 1.019 | 0.12 |

NQ-contract-equivalent reading (×20 PV): Net ≈ **$18,460**, stress DD ≈ **−$157k**.

## Vs NQ Databento (same window ≤ 2025-10-01)

Source: `live/state/nq_v2b_prior_opposed_stpmc_broker_like` filtered to entry ≤ 2025-10-01.

| | NAS100 CFD | NQ futures |
|---|---:|---:|
| Campaigns | 310 | 310 |
| Entry-session overlap | 291 / 329 union (88%) | — |
| Direction agree (overlap) | 99.3% | — |
| Win % | ~47 | ~68 |
| Profit factor | ~1.02 | ~2.45 |
| Net (native) | $923 | $886,105 |
| Net (NAS×20) | ~$18.5k | $886k |

**Shape:** timing/direction track NQ closely (same OR breaks often to the minute).
**Edge:** not similar — NAS100 is near breakeven after fees; NQ keeps a strong PF on the same dates. CFD basis + `$1.50` fee on `$1`/pt economics explain much of the dollar gap; win-rate gap means it is not pure point-value scaling.

## Causality / gate

- Regime sessions replayed: **1027**
- Replay start: **2021-03-04**
- Data end: **2025-10-01**
- Prior-opposite entries found: **310 / 310**
- Causal violations: **0**
- Direction mix: **131 long / 179 short**

Files:

- `summary.csv`
- `states/nas100_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- Driver: `live/nas100_prior_opposed_replay.py`
