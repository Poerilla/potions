# NQ v2b Prior-Opposed ST+PMC Broker-Like Replay

True `Engine + PaperBroker + StrategyPlugin` replay using the **legacy hourly
left-label ST fill stamp** as the prior-opposed gate.

**2026-07-15:** This long-history tape inherits the same timestamp inflation as
the 2021-start banked book. NQ promotion candidate is **resting-limit**
([`../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md));
re-run full history with resting-limit before treating Net/Stress as promotion truth.

Separate long-history raw-data run using restored NQ 1m DBN:

- Raw 1m source: `nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst`
- Daily regime file: `nq/nq_daily.csv`
- ST+PMC gate fills: `live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/combined_state/fills.csv`
- Effective support window: daily/gate support runs through **2026-03-08 / 2026-03-05** even though the raw DBN extends to 2026-06-16.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 877 | 4385 | $1713277.50 | $-53172.00 | $-53847.00 | 64.77 | 2.427 | 31.82 |

## Causality

- Regime sessions replayed: **3056**
- Replay start: **2010-06-06**
- Prior-opposite entries found: **877 / 877**
- Causal violations: **0**
- Direction mix: **364 long / 513 short**

## Comparison vs banked 2021-start run

| Window | Campaigns | Units | Net | Closed DD | Stress DD | Win % | PF | Net/Stress |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full history raw, start 2010-06-06 | 877 | 4,385 | $1,713,277.50 | $-53,172.00 | $-53,847.00 | 64.77 | 2.427 | 31.82 |
| Banked run, start 2021-03-04 | 352 | 1,760 | $1,184,585.00 | $-53,172.00 | $-53,847.00 | 69.32 | 2.654 | 22.00 |

Read: the earlier history adds **525 campaigns** and **$528,692.50** of net before 2021-03-04 without deepening the full-window closed or intrabar stress DD. The newer 2021+ segment has the higher win rate and PF, but the long-history result materially strengthens the sample.

## Annual campaign breakdown

| Year | Campaigns | Net | Win % | PF | Campaign closed DD | Net/DD |
|---:|---:|---:|---:|---:|---:|---:|
| 2011 | 30 | $7,110.00 | 63.33 | 1.987 | $-2,482.50 | 2.86 |
| 2012 | 31 | $10,832.50 | 64.52 | 1.932 | $-2,900.00 | 3.74 |
| 2013 | 36 | $3,195.00 | 47.22 | 1.226 | $-4,320.00 | 0.74 |
| 2014 | 58 | $21,965.00 | 62.07 | 1.629 | $-7,222.50 | 3.04 |
| 2015 | 56 | $43,110.00 | 67.86 | 2.557 | $-6,435.00 | 6.70 |
| 2016 | 43 | $36,417.50 | 72.09 | 2.317 | $-9,360.00 | 3.89 |
| 2017 | 58 | $8,755.00 | 53.45 | 1.236 | $-12,132.50 | 0.72 |
| 2018 | 72 | $68,495.00 | 55.56 | 1.818 | $-17,930.00 | 3.82 |
| 2019 | 60 | $66,325.00 | 61.67 | 2.742 | $-7,117.50 | 9.32 |
| 2020 | 67 | $174,742.50 | 64.18 | 1.998 | $-40,937.50 | 4.27 |
| 2021 | 91 | $360,887.50 | 74.73 | 4.219 | $-12,107.50 | 29.81 |
| 2022 | 16 | $13,425.00 | 56.25 | 1.170 | $-31,382.50 | 0.43 |
| 2023 | 73 | $168,292.50 | 68.49 | 2.430 | $-34,652.50 | 4.86 |
| 2024 | 93 | $199,522.50 | 64.52 | 1.889 | $-24,945.00 | 8.00 |
| 2025 | 74 | $399,000.00 | 71.62 | 4.086 | $-22,815.00 | 17.49 |
| 2026 | 19 | $131,202.50 | 84.21 | 5.703 | $-15,465.00 | 8.48 |

Files:

- `summary.csv`
- `comparison_vs_2021_start.csv`
- `yearly_breakdown.csv`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
