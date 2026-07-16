# v2b Prior-Opposed ST+PMC Execution Scrutiny

This is an execution and live-readiness audit only. Strategy rules and sizing are frozen.

**2026-07-15:** Numbers below are from the **legacy hourly left-label ST fill-stamp** books. For NQ that tape is **timestamp-inflated**; the NQ promotion candidate is **resting-limit** ([`../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md)). Re-run this scrutiny pack on resting-limit before live funding.

| Market | Campaigns | Net | Win % | PF | Causal violations | Bar-safe | Ambiguous <=1m | Pre-arm touch | Later level retest | Trigger-only later touch | No later 1m touch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ *(legacy fill stamp)* | 352 | $1184585.00 | 69.32 | 2.747 | 0 | 141 | 45 | 166 | 146 | 64 | 1 |
| MNQ | 353 | $113547.50 | 68.56 | 2.615 | 0 | 142 | 44 | 167 | 147 | 63 | 1 |
| ES | 245 | $348687.50 | 63.67 | 2.180 | 0 | 95 | 22 | 128 | 113 | 36 | 1 |
| YM | 347 | $320190.00 | 59.65 | 1.887 | 0 | 187 | 38 | 122 | 114 | 44 | 2 |
| MYM | 333 | $26053.62 | 59.76 | 1.742 | 0 | 177 | 33 | 123 | 111 | 44 | 1 |

Important: 1m bars cannot prove 200ms execution safety. The retest columns are coarse estimates only: `later_level_retest` means a later 1m bar spans the entry level before exit; `later_trigger_touch_only` means the trigger side appears again but the exact level is not proven; `no_later_touch_in_1m` is the rough completely-missed bucket. Campaigns in `ambiguous_same_1m_bar` and `pre_arm_breakout_touch` are still routed to each market's `tick_replay_manifest.csv` for Databento/broker tick reconstruction.

ES/YM/MYM use the same strict delayed-arming plugin gate and were replayed on full-RTH sessions only after the first YM/MYM pass exposed two early-close / holiday entries with no normal 15:55 flatten. The cleaned ES/YM/MYM fill books have zero entry-without-exit campaigns.

- NQ: [`nq/SCRUTINY_REPORT.md`](nq/SCRUTINY_REPORT.md)
- MNQ: [`mnq/SCRUTINY_REPORT.md`](mnq/SCRUTINY_REPORT.md)
- ES: [`es/SCRUTINY_REPORT.md`](es/SCRUTINY_REPORT.md)
- YM: [`ym/SCRUTINY_REPORT.md`](ym/SCRUTINY_REPORT.md)
- MYM: [`mym/SCRUTINY_REPORT.md`](mym/SCRUTINY_REPORT.md)
