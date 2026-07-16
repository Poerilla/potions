# NQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay using the **legacy hourly
left-label ST fill stamp** as the prior-opposed gate.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 352 | 1760 | $1175785.00 | $-53267.00 | $-53942.00 | 69.32 | 2.633 | 21.80 |

## Status (2026-07-15)

**Diagnostic / timestamp-inflated.** Hourly ST fills are stamped at the left
edge of the fill hour, so the gate can arm before the true 1m limit touch.
Timing autopsy attributes ~76–78% of this net to lookahead victims.

**NQ promotion candidate:** resting-limit gate (arm when opposite ST limit is
posted / `live_after_ts`):
[`../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md)
(**434** campaigns / **$1,321,745** / **-$68,610** stress / **19.26** Net/Stress).

Related:

- Timing autopsy: [`../nq_v2b_prior_opposed_timing_study/INDEX.md`](../nq_v2b_prior_opposed_timing_study/INDEX.md)
- Strict 1m-touch fill gate: [`../nq_v2b_prior_opposed_stpmc_1m_touch/INDEX.md`](../nq_v2b_prior_opposed_stpmc_1m_touch/INDEX.md)
- Proxy comparison: [`../nq_v2b_prior_opposed_causal_proxies/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/INDEX.md)

## Causality (within this legacy tape)

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **352 / 352**
- Causal violations vs hourly stamp: **0** (does **not** prove 1m-knowable fill time)
- Direction mix: **147 long / 205 short**

Files:

- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
