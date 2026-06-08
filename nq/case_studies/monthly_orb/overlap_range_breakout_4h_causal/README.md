# Monthly ORB Overlap Range Breakout - 4H Causal Stop/Limit Cycle

This rewrites the older daily-close overlap-range breakout into the causal 4-hour engine used by the restricted stop/limit cycle.

Rules in this pass:

- Default **long** side: buy stop at the combined range high; optional **`--side short`** (or **`--side both`**) runs a mirrored sell-stop breakout at the combined range low (`breakout_only` only), writing separate `Run_Variant` rows and files (`*_short`) for side-by-side live tests.
- Monthly OR = first three daily rows of each calendar month.
- Adjacent overlapping monthly ORs become one combined range; later overlapping months can expand that range.
- After the combined range is active, the resting primary is a buy stop at the range high (long) or a sell stop at the range low (short, breakout-only path).
- Stop-breakout package uses **3 contracts**: 1 @ TP50, 1 @ TP1, 1 runner @ TP2.
- A failed stop-breakout can arm the bottom-range limit only after at least one 4-hour candle closed above the range.
- Bottom-limit package uses 3 contracts: 1 off at the top boundary and 2 off at TP1.
- TP1 arms a 2-contract top refill while the original runner may remain open.
- Max two primary attempts per overlap cluster; top refills do not count as new primary attempts.
- Runs with a `2 active max` label allow one older overlap trade to remain open while a newer overlap cluster takes one package.
- `ST reclaim scale-in` risk-on runs add contracts only after a confirmed daily Supertrend bearish flip during an open long runner; the stored bearish stop level becomes a 4h-close reclaim trigger and a 4h-close stop for those added contracts.
- `ST limit retest` risk-on runs place a 5-contract long limit at the confirmed daily Supertrend trailing stop while an original breakout runner is open; the add exits with that runner or on a 4h close below the current confirmed daily Supertrend stop.
- Daily-close invalidations are shown in both close-fill and next-open-fill modes.

## Summary

| Market | Variant | Exit fill | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts | Bottom limits | Top refills | TP1-hit rows |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 23 | 43,793.1 | $87,586 | $-4,775 | 60.9% | 8.26 | 252.1 | 806.8 | 0 | 0 | 69.6% |

## Read

- **Full cycle first pass** is banked here as the original causal overlap-cycle run.
- **Breakout only** removes bottom-limit reclaims and top refills. It keeps the 3-contract stop-breakout (long at range high; use `--side short` for the mirrored short at range low, separate outputs).
- The first-pass read still matters: in the full cycle, the edge was concentrated in the Stop-Breakout packages while the inherited Bottom-Limit and Top-Refill components were net-negative.

## Winner Drawdown Profile

Depth means the winner’s maximum adverse excursion measured from entry back into the combined range.
For a breakout entry, 25% depth means price came one quarter of the overlap range back inside before eventually winning.

| Market | Variant | Exit fill | Winners | Avg depth | Max depth | <=25% | 25-50% | 50-100% | >100% |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 14 | 17.8% | 43.0% | 9 | 5 | 0 | 0 |

Worst winning pullbacks:

| Market | Variant | Exit fill | Cluster | Entry | MAE pts | Depth | Net USD |
|---|---|---|---|---|---:|---:|---:|
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 12 2024-03+2024-04+2024-05 | 2024-05-15T12:00:00-04:00 | 588.2 | 43.0% | $3,374 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 13 2024-08+2024-09 | 2024-09-17T00:00:00-04:00 | 576.8 | 38.4% | $3,475 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 17 2025-07+2025-08 | 2025-08-19T20:00:00-04:00 | 338.2 | 34.9% | $7,754 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 9 2023-04+2023-05 | 2023-05-10T08:00:00-04:00 | 104.5 | 32.2% | $2,270 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 8 2023-02+2023-03 | 2023-03-22T12:00:00-04:00 | 315.2 | 28.2% | $7,830 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 4 2020-09+2020-10+2020-11 | 2020-12-01T11:00:00-05:00 | 258.5 | 16.2% | $11,706 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 14 2024-10+2024-11 | 2024-11-15T11:00:00-05:00 | 73.4 | 14.3% | $9,031 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 16 2025-04+2025-05 | 2025-05-08T08:00:00-04:00 | 219.5 | 13.0% | $11,800 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 11 2023-10+2023-11 | 2023-11-06T07:00:00-05:00 | 90.5 | 11.1% | $5,722 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 14 2024-10+2024-11 | 2024-11-05T11:00:00-05:00 | 51.5 | 10.0% | $3,594 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 13 2024-08+2024-09 | 2024-11-15T11:00:00-05:00 | 73.4 | 4.9% | $10,156 |
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 15 2024-12+2025-01 | 2025-02-02T15:00:00-05:00 | 21.0 | 3.4% | $1,208 |

Per-trade winner drawdown CSV: `mnq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/winner_drawdown_by_trade.csv`

## Loss Containment Scan

| Market | Variant | Exit fill | Losses | Gross loss USD | Worst loss USD | Avg losing depth | Max losing depth | Main exit reason |
|---|---|---|---:|---:|---:|---:|---:|---|
| MNQ | Breakout only (2 active max) — Daily ST filter + ST limit retest x5 | close | 9 | $-12,069 | $-4,138 | 44.3% | 99.9% | Daily-Close-25pct-Back-In-Range-Before-TP1 |


## Entry Kind Split

### MNQ - Breakout only (2 active max) — Daily ST filter + ST limit retest x5 - close

| Entry kind | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Daily-ST-Limit-Retest-Scalein | 7 | 18,600.0 | $37,200 | $-1,054 | 57.1% | 33.30 |
| Stop-Breakout | 16 | 25,193.1 | $50,386 | $-4,775 | 62.5% | 5.62 |

## Yearly Split

### MNQ - Breakout only (2 active max) — Daily ST filter + ST limit retest x5 - close

| Year | Trades | Net pts | Net USD | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 2 | 1,858.4 | $3,717 | 1 | 1 | 26.2 | 51.4 |
| 2020 | 1 | 5,852.9 | $11,706 | 1 | 0 | 258.5 | 258.5 |
| 2021 | 2 | -2,087.5 | $-4,175 | 0 | 2 | 446.3 | 806.8 |
| 2022 | 1 | -31.8 | $-64 | 0 | 1 | 272.2 | 272.2 |
| 2023 | 4 | 7,624.4 | $15,249 | 3 | 1 | 157.1 | 315.2 |
| 2024 | 6 | 23,793.8 | $47,588 | 6 | 0 | 227.2 | 588.2 |
| 2025 | 6 | 8,454.0 | $16,908 | 3 | 3 | 267.0 | 619.0 |
| 2026 | 1 | -1,671.0 | $-3,342 | 0 | 1 | 729.8 | 729.8 |

## Cluster Events

### MNQ - Breakout only (2 active max) — Daily ST filter + ST limit retest x5 - close

- skip_daily_supertrend_not_bullish: **73**
- expand: **19**
- start: **18**
- fill_stop: **16**
- fill_daily_st_limit_retest_scalein: **7**
- extend_target: **3**

## Outputs

- `mnq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/mnq_overlap_range_breakout_4h_causal_breakout_only_2active_daily_st_retest5_close.csv`
- `mnq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/mnq_overlap_range_breakout_4h_causal_breakout_only_2active_daily_st_retest5_close_events.csv`
- `mnq/case_studies/monthly_orb/overlap_range_breakout_4h_causal/winner_drawdown_by_trade.csv`
- [charts_mnq_breakout_only_2active_daily_st_retest5_close](charts_mnq_breakout_only_2active_daily_st_retest5_close/INDEX.md)

Hardening note: this is still built from the existing daily first-three-row monthly OR definition. Before live use, the OR calendar/session definition should be made explicit exactly as noted in the restricted-cycle hardening notes.
