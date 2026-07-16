# NQ Provisional All-Regime v2b + Invalidate 60m

True `Engine + PaperBroker + StrategyPlugin` replay. Trades all regime v2b days;
flattens if no opposite 1m-touch ST fill within **60 minutes** of entry.

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1268 | 6340 | $467,747.50 | $-130,389.75 | **$-131,314.75** | 53.31 | 1.135 | 3.56 |

## Causality / gate

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Gate mode: provisional (all regime) + `invalidate_without_opposite_minutes=60`
- Prior-opposite ST fills confirmed at entry: **104 / 1268**
- Causal violations: **0**
- Direction mix: **650 long / 618 short**
- Invalidate without opposite ST within **60** minutes of entry (**664** invalidate exits)

## ST+PMC 1m first-touch timestamps (for invalidate check)

- Gate events: **1697**
- Resolved 1m touches: **1697**
- Unresolved (kept hourly stamp): **0**
- Touches outside fill hour: **0**
- Median delay vs hourly stamp: **28.0 min**

Files:

- `summary.csv`
- `states/nq_v2b_provisional_stpmc_S_1_1_3/`
