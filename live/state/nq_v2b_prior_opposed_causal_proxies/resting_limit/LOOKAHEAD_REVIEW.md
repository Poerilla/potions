# NQ Resting-Limit Hour-Complete — Lookahead Re-Review (2026-07-16)

Verdict: **SOLID** for minute-by-minute causal execution matching this baseline.

## Checks passed

- Gate availability = ST `live_after + 1h` (hour-complete), matching when ST+PMC posts.
- Strategy uses `available_at_ts` with strict `<` current 1m bar (no same-bar gate use).
- Sampled banked arms: **0** campaigns with `arm_ts <= enabling available_at` (min lag 1m).
- OR from 15 completed 1m bars; regime filter uses prior-day MA only.
- Broker blocks fills on the arming bar.

## Residual (not lookahead)

- OHLC path uncertainty on stop/limit fills (execution realism).
- Cancelled ST entry limits still count as gate events (posted-at-hour-complete semantics).
- Dense RTH 1m fill-forward for missing minutes.

Live/automation that waits for the completed ST hour, then arms opposite v2b on later 1m bars, can target this book’s gate causality.
