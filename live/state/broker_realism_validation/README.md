# Broker Realism Validation

This report validates the 2026-05-20 `PaperBroker` realism changes with known-answer broker fills and real MNQ/NQ front-month 4h samples from the 1m-derived cache.

## Review Read

- Stop gap-through modeling is conservative and realistic for bar replay: a stop touched after the market opens beyond the trigger fills at the bar open, not the stale stop price.
- One adverse tick on market/stop-style fills is a reasonable default for futures paper replay. Limit orders remain capped at the limit price with no modeled price improvement.
- Stop-first same-bar ordering is intentionally pessimistic for protective exits when a candle contains both target and stop.
- OCO risk projection now counts only the largest peer in the group, which matches real OCO exposure better than summing both sides.
- `market_close` also gets market-style slippage. That is conservative for a 15:59 flatten proxy; if we later use true exchange MOC orders, this should become a separate knob.

## Test Cases

| Case | Expected | Actual | Pass | Chart |
|---|---:|---:|---:|---|
| Buy stop gap-through | 103.25 | 103.25 | yes | [charts/01_buy_stop_gap_through.png](charts/01_buy_stop_gap_through.png) |
| Sell stop gap-through | 96.75 | 96.75 | yes | [charts/02_sell_stop_gap_through.png](charts/02_sell_stop_gap_through.png) |
| Stop-first ambiguity | stop at 97.75 | stop at 97.75 | yes | [charts/03_stop_first_same_bar_ambiguity.png](charts/03_stop_first_same_bar_ambiguity.png) |
| Strict market-close | no 15:59 fill; 100.55 at 16:00 | early=0, fill=100.55 | yes | [charts/04_strict_market_close.png](charts/04_strict_market_close.png) |
| OCO risk projection | second OCO allowed; extra ladder blocked | second=ok, ladder=max_contracts_exceeded | yes | [charts/05_oco_risk_projection.png](charts/05_oco_risk_projection.png) |
| Audit fee subtraction | $18.50 | $18.50 | yes | [charts/06_fee_audit.png](charts/06_fee_audit.png) |
| Real MNQ 4h buy-stop gap-through sample | 19164.00 | 19164.00 | yes | [charts/07_real_mnq_buy_stop_gap.png](charts/07_real_mnq_buy_stop_gap.png) |
| Real MNQ 4h sell-stop gap-through sample | 17126.00 | 17126.00 | yes | [charts/08_real_mnq_sell_stop_gap.png](charts/08_real_mnq_sell_stop_gap.png) |
| Real NQ 4h buy-stop gap-through sample | 19225.25 | 19225.25 | yes | [charts/07_real_nq_buy_stop_gap.png](charts/07_real_nq_buy_stop_gap.png) |
| Real NQ 4h sell-stop gap-through sample | 17099.75 | 17099.75 | yes | [charts/08_real_nq_sell_stop_gap.png](charts/08_real_nq_sell_stop_gap.png) |

## Remaining Caveats

- Timestamps are still compared as sortable strings. This is fine when every replay uses consistent ISO/date strings, but mixed timezone formats should be normalized before live routing.
- Same-bar OCO entry ambiguity is deterministic by order creation order. The stop-first rule protects exit realism; it does not infer whether the high or low came first inside a candle.
- Partial fills, bid/ask spread, exchange halts, margin liquidation, and broker-specific order-routing behavior are still outside this paper model.
