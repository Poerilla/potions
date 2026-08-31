# US30 ST+PMC signal-hour attribution (retired fair-3R)

Source: pre–completed-hour `sl50_tp150_3r_1mfill` campaigns (N/S 29.39 lot-correct / ~20.97 raw MTM). Diagnostic only.

## Headline

- Campaigns attributed: **578**
- Same-hour fills under old arming: **74 (12.8%)**
- Target reached before hour close: **418**
- Stop reached before hour close: **24**
- Post-close ST-limit retest within 24h: **521 (90.1%)**
- Post-close continuation (break signal-hour H/L) within 24h: **315 (54.5%)**

## Buckets

| bucket | n |
|---|---:|
| `post_close_fill_under_old_arming` | 504 |
| `same_hour_lookahead_fill` | 29 |
| `same_hour_stop_before_close` | 24 |
| `same_hour_target_before_close` | 21 |

## Fields

Per-trade CSV: `attribution.csv` — hour_start/close, old vs earliest causal entry, MFE/MAE before hour close, post-close retest/continuation flags.

## Demo decision

See [`DEMO_DECISION.md`](DEMO_DECISION.md). Alpha status: **invalidated**.

## Next

Paths A/B/C are **new** causal strategies — hub `live/state/us30_st_pmc_causal_revival_abc/`.

