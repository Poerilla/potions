# v2b Prior-Opposed Resting-Limit Hour-Complete (Cross-Market)

Gate: opposite ST+PMC entry limit knowably resting at **hour-complete** (`live_after + 1h`).
NQ lookahead re-review: **SOLID** for minute-by-minute execution
([`../nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md)).

| Market | Campaigns | Net | MTM Stress | Win % | PF | Net/Stress | vs legacy fill net | Path |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **NQ** | 432 | $1,330,920 | $-68,610 | 66.0 | 2.33 | **19.40** | +155,135 | [`causal_proxies/resting_limit`](../nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md) |
| **MNQ** | 428 | $128,360 | $-6,960 | 65.4 | 2.26 | **18.44** | +13,390 | [`mnq_v2b_prior_opposed_stpmc_resting_limit`](../mnq_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| **YM** | 436 | $289,225 | $-33,894 | 61.0 | 1.59 | **8.53** | -29,566 | [`ym_v2b_prior_opposed_stpmc_resting_limit`](../ym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| **MYM** | 423 | $22,101 | $-3,417 | 60.5 | 1.46 | **6.47** | -3,987 | [`mym_v2b_prior_opposed_stpmc_resting_limit`](../mym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| ES | — | — | — | — | — | — | legacy fill $348,688 | **1m DBN missing** |

## Notes

- Legacy hourly-fill-stamp books remain under `*_stpmc_broker_like/` as diagnostics.
- ES resting-limit rerun blocked until `es/raw/...ohlcv-1m.dbn.zst` is restored.
- All completed markets: **0** fill-book causality violations.

Files: `comparison.csv`
