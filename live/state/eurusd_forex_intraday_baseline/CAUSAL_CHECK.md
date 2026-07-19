# Causal / Lookahead Check — EURUSD Forex Intraday Baseline

**Strategy:** `eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`  
**Plugin:** `HourlyStPmcRetestStrategy` (`ma_filter=bull_prior_only`)  
**Verdict: PASS** (2026-07-17)

## What was checked

| Check | Result |
|---|---|
| `causality_violations.csv` rows | **0** |
| Entry fills with `fill.ts <= order.live_after_ts` | **0 / 1148** |
| Min fill lag after `live_after_ts` | **1 hour** (median **6 hours**) |
| Feature `available_at_ts` after `current_bar_ts` | **0** |
| Feature `event_ts` after `available_at_ts` | **0** |
| Entry orders stamped on hour boundary | **100%** |

## Rule causality (code)

1. **Hour-complete only.** `on_bar_close` runs only when `bar.timeframe == "1h"` and `bar.complete`.
2. **`live_after_ts = confirming hour close.** Resting limits cannot fill on the signal bar; broker requires a strictly later bar.
3. **SuperTrend** is updated from completed hourly OHLC only (incremental ATR trail).
4. **Prior-month close (PMC)** is the last close of the *previous* calendar month — available from month start.
5. **MA bull prior gate** uses **prior completed hour** MA50 vs MA150 (`n-1`), not the current bar’s MAs — avoids same-bar MA lookahead on the filter.
6. Replay path is `Engine + PaperBroker` with 1-tick slippage and fee=$1.50/unit (see MTM audit).

## Residual notes

- OHLC path ambiguity remains (stop-first same-bar is pessimistic). Not lookahead.
- Book is hourly-bar replay (fills evaluate on subsequent hours), so intra-hour touch timing is coarser than a 1m path — conservative on timing, not optimistic.

Artifact: `causal_check.json`
