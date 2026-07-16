# NQ Prior-Opposed Causal Proxy Comparison

Timing autopsy: `live/state/nq_v2b_prior_opposed_timing_study/INDEX.md`

**2026-07-16:** Resting-limit baseline now uses **hour-complete** availability
(`live_after + 1h`). Left-label resting-limit is diagnostic only.

Intrabar stress DD is the portfolio **MTM / intrabar stress** drawdown.

| Label | Trades | Net | Closed DD | MTM / Stress DD | Win % | PF | Net/Stress | Prior@entry |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **resting_limit (causal baseline)** | 432 | **$1,330,920** | $-68,110 | **$-68,610** | 65.97 | 2.326 | **19.40** | 432 |
| resting_limit_left_label (diagnostic) | 434 | $1,321,745 | $-68,110 | $-68,610 | 65.67 | 2.300 | 19.26 | 434 |
| provisional_confirm_resting_st_60m | 1,279 | $878,900 | — | $-97,692 | — | — | 9.00 | — |
| provisional_invalidate_60m (1m-touch confirm) | 1,268 | $467,748 | $-130,390 | $-131,315 | 53.31 | 1.135 | 3.56 | 104 |
| banked_hourly_stamp (inflated) | 352 | $1,175,785 | $-53,267 | $-53,942 | 69.32 | 2.633 | 21.8 | 352 |
| fill_1m_touch (strict fill gate) | 350 | $225,825 | $-152,412 | $-153,087 | 48.86 | 1.203 | 1.48 | 350 |

## Proxies

- **resting_limit (baseline):** arm after opposite ST entry limit is knowably
  resting at **hour-complete**. Still filters (**432 / 1,164**). Early-sleeve
  PnL is recovered by delaying arm ~60m; median entry delay **0**. See
  [`early_pnl_recovery/INDEX.md`](early_pnl_recovery/INDEX.md).
- **resting_limit_left_label:** same events stamped at left-label (lookahead) —
  diagnostic only.
- **provisional_confirm_resting_st_60m:** all-regime v2b; flatten if no opposite
  hour-complete ST resting within 60m — weaker than gated baseline.
- **fill_1m_touch / banked_hourly_stamp:** fill-gate family (not promotion).

## Files

- `comparison.csv`
- `resting_limit/`
- `resting_limit_left_label_diagnostic/`
- `early_pnl_recovery/`
- `provisional_confirm_resting_st_60m/`
- `provisional_invalidate_60m/`
