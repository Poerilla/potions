# NQ Resting-Limit True Rerun: entry_live_after_delay=1m

True `Engine + PaperBroker + StrategyPlugin` replay with
`entry_live_after_delay_minutes=1.0`: when v2b decides to arm, the entry stop’s
`live_after_ts` is pushed forward by 1 minute so it cannot fill on the immediate
next 1m bar. Same-day reverse / re-arm sequencing can change.

Hub: `live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit_entry_delay_1m/`

| Metric | Baseline resting-limit | Post-filter exclude <=1m | TRUE delay 1m rerun |
|---|---:|---:|---:|
| Campaigns | 432 | 331 | 431 |
| Units | 2,160 | 1,655 | 2,155 |
| Net | $1,330,920 | $1,042,682 | $1,326,222 |
| Closed DD | $-68,110 | $-47,732 | $-70,485 |
| Intrabar stress DD | $-68,610 | $-49,691 | $-70,985 |
| Win % | 65.97 | 66.47 | 65.20 |
| PF | 2.326 | 2.444 | 2.344 |
| Net/Stress | 19.40 | 20.98 | 18.68 |

## Read

- Delaying stop activation by 1m barely moves the book: **99.6% of baseline net**, −1 campaign.
- That is **not** the same as the post-filter (drop all arm→fill ≤1m campaigns), which removed ~$288k net and lifted N/S to 20.98.
- After the delay, measured `live_after → fill` still has **107** fills at exactly 1.0 minute — delaying activation just shifts the clock; next-bar fills after the new `live_after` remain.

Stance: **retain baseline resting-limit**. The true 1m activation delay is a mild sequencing tweak, not a substitute for the post-filter stress test. Do not promote a live “delay 1m” rule from this alone; the edge is not dependent on undelayed next-bar captures, but the delay also does not improve N/S.

## Files

- `summary.csv`, `INDEX.md`, `EMAIL.txt`
- `states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/`
- Baseline: `../resting_limit/`
- Post-filter: `../resting_limit/latency_filter_exclude_arm_to_fill_lte_1m/`
