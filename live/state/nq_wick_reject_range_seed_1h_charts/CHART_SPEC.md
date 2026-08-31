# CHART_SPEC — NQ limit-retest 1h / 2-week visual audit pack

**study_source:** `live/state/nq_wick_reject_range_seed_retest/`
**population:** all **67** `primary_limit_retest` **FILLED** campaigns (frozen tape)
- development fills: 53
- holdout fills: 14

## Geometry
- timeframe: **1-hour** RTH candles
- window: **7 calendar days before → 7 calendar days after** each **entry fill_ts**
- overlays from frozen campaign/event records only:
  - seeded 4h WICK_REJECT range **high / low / midpoint**
  - yellow confirm 4h span
  - seed `available_at`
  - 1h break confirmation
  - retest-limit activation (`order_live_at`) and actual fill
  - opposite-range stop
  - TP1/TP2/runner (0.5W / 1W / 2W) and exit annotation

## Causal timestamp assertions
Required ordering on every chart / manifest row:
`seed_available_at < break_confirm_ts < order_live_at <= fill_ts`

## Subsets
| subset | n | path prefix |
|---|---:|---|
| all_filled | 67 | `charts/all/` |
| holdout | 14 | `charts/holdout/` |
| balanced_review | 12 | `charts/balanced_review/` |

Balanced-review = stratified sample up to 3 per (side × win/loss) cell, holdout preferred then extreme |R|.

## Artifacts
- `CHART_SPEC.md` (this file)
- `INDEX.md` / `INDEX_holdout.md` / `INDEX_balanced_review.md`
- `chart_manifest.csv`
