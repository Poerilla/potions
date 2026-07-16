# NQ v2b Prior-Opposed Strict 1m-Touch Fill Gate

True `Engine + PaperBroker + StrategyPlugin` replay. Arms v2b only after the
same-session opposite ST+PMC entry limit has **actually filled**, timed at the
first 1m limit touch after `live_after_ts`.

| Trades | Units | Net | Closed DD | Intrabar / MTM Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 350 | 1750 | $225,825.00 | $-152,412.00 | **$-153,087.00** | 48.86 | 1.203 | 1.48 |

## Causality

- Regime sessions replayed: **1164**
- Replay start: **2021-03-04**
- Prior-opposite entries found: **350 / 350**
- Causal violations: **0**
- Direction mix: **147 long / 203 short**

## ST+PMC 1m first-touch gate timestamps

Hourly left-labeled ST fills are refined to the first 1m limit touch after `live_after_ts`.

- Gate events: **1697**
- Resolved 1m touches: **1697**
- Unresolved (kept hourly stamp): **0**
- Touches outside fill hour: **0**
- Median delay vs hourly stamp: **28.0 min**

## Comparison vs banked hourly-stamp gate

Banked reference: `live/state/nq_v2b_prior_opposed_stpmc_broker_like/` (**diagnostic / timestamp-inflated**).
NQ promotion candidate is resting-limit:
[`../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md).

| Metric | Hourly stamp (banked) | First 1m touch | Delta |
|---|---:|---:|---:|
| Campaigns | 352 | 350 | -2 |
| Net | $1,175,785.0 | $225,825.0 | $-949,960.00 |
| Closed DD | $-53,267.0 | $-152,412.0 | $-99,145.00 |
| Intrabar / MTM stress DD | $-53,942.0 | **$-153,087.0** | $-99,145.00 |
| Win % | 69.32 | 48.86 | -20.46 |
| PF | 2.633 | 1.203 | -1.430 |
| Net/Stress | 21.8 | 1.48 | -20.32 |
| Causal violations | 0 | 0 | 0 |

Matched-session entry timing (350 overlapping campaign days):

- Same entry minute: **123**
- Later entry after 1m refinement: **227**
- Earlier entry: **0**
- Median entry delay: **4.0 min**
- Campaigns with lower / higher / equal PnL: **206 / 10 / 134**

Read: causality still clean (**0** violations). Removing optimistic hour-open ST stamps collapses Net/Stress to **1.48**. Do not promote this fill-gate as the NQ flagship; use resting-limit instead.

Files:

- `comparison_vs_hourly_stamp.csv`
- `summary.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
