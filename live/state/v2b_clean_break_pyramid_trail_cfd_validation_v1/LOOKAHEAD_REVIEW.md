# NAS100 Clean-Break Pyramid Trail Lookahead Review

**Date:** 2026-08-31  
**Scope:** NAS100 Scenario 0 frozen variants in `v2b_clean_break_pyramid_trail_cfd_validation_v1`.  
**Status:** NAS100 reproduces and passes order-time causality checks. The best-N/S frozen candidate now has a stricter 1m-fill validation with feature snapshots; it remains **research-only** because true historical tick/bid-ask quote equivalence is not proven.

## Fresh Rerun

Command:

```bash
env PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src python -m live.v2b_clean_break_pyramid_trail_cfd_validation_v1 --scenario S0_base
```

Ledger row: `brl_20d2a2fe8e78`

The validation driver is CFD-basket scoped, so the overall disposition remains `NON-REPRODUCIBLE` because US30/SPX500 parent deltas exceed tolerance. NAS100 itself reproduced the parent S0 values within floating-point dust.

## NAS100 Reproduction

| Variant | Sessions | Trades | Units | Net | Stress DD | N/S | Win % | PF | Parent delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `trail06_m4_e2_out_be` | 2,277 | 1,166 | 2,077 | $11,331.50 | -$1,960.90 | 5.78 | 27.2% | 1.39 | ~$0.00 |
| `trail06_m4_e1_opp_be` | 2,277 | 1,166 | 2,081 | $10,844.00 | -$2,087.40 | 5.19 | 25.1% | 1.39 | ~$0.00 |
| `trail06_m8_e2_out_be` | 2,277 | 1,166 | 2,848 | $18,868.80 | -$3,975.10 | 4.75 | 34.4% | 1.44 | ~$0.00 |

Read: best NAS100 N/S is `trail06_m4_e2_out_be`; best NAS100 net is `trail06_m8_e2_out_be`, which is the charted win/loss pack.

## Order-Time Causality Checks

Direct audit over each NAS100 S0 `orders.csv` + `fills.csv`:

| Variant | Entry fills | Non-MOC fills at/before `live_after_ts` | MOC fills before `live_after_ts` | Entry fills at/before arm | Feature snapshots | Causal violations |
|---|---:|---:|---:|---:|---:|---:|
| `trail06_m4_e2_out_be` | 1,166 | 0 | 0 | 0 | 0 | 0 |
| `trail06_m4_e1_opp_be` | 1,166 | 0 | 0 | 0 | 0 | 0 |
| `trail06_m8_e2_out_be` | 1,166 | 0 | 0 | 0 | 0 | 0 |

The shared `PaperBroker` requires non-market fills to occur strictly after `live_after_ts`, and the fresh replay has no entry fills before activation.

## 1m-Fill Validation Added

Follow-up run:

```bash
env PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src python -m live.nas100_clean_break_best_1mfill_quote_validation
```

Hub: [`../nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/SUMMARY.md`](../nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/SUMMARY.md)  
Ledger row: `brl_21741b260a28`

This run keeps completed 5m candles as signal-only and fills orders only on the local NAS100 1m tape with synthetic bid/ask sidecar fields.

| Candidate | Sessions | Trades | Units | Net | Stress DD | N/S | Feature snapshots | Causality violations | Non-MOC fills at/before activation | Entry fills at/before activation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `trail06_m4_e2_out_be` | 2,277 | 1,166 | 2,070 | $12,252.95 | -$1,965.85 | 6.23 | 22,558 | 0 | 0 | 0 |

Read: the frozen best-N/S NAS100 candidate survives the finer 1m fill pass. The unit count changes versus 5m-only because market/stop/clean-close sequencing is now matched on the 1m tape, but the headline efficiency improves slightly from **5.78** to **6.23**.

## Causal Mechanics Reviewed

- Opening range uses completed 5m RTH bars for 09:30, 09:35, and 09:40.
- The buy stop is submitted after OR finalization with `live_after_ts` set to the confirming bar timestamp.
- `PaperBroker` processes existing orders before strategy evaluation on each bar and then processes newly submitted orders after strategy evaluation; non-market orders still cannot fill on the same bar because of the strict `live_after_ts` check.
- Clean-break validation uses the completed fill bar close. If the close fails validation, the strategy submits a reduce-only `market_close` flatten for that same bar.
- Pyramid adds, soft exits, and trail/target refreshes are generated from completed 5m bars. Adds and newly armed trail/target orders fill from later bars under the broker model.

## Live-Match Gaps

These are not confirmed lookahead bugs, but they prevent a live/paper-ready claim:

1. **True quote history is still missing.** The 1m validation uses synthetic bid/ask fields from local NAS100 OHLC, not actual historical broker tick/quote data.
2. **5m candle timestamps are left-labeled.** The 1m-fill driver delivers each 5m signal only after the constituent 1m rows have processed, but the persisted signal bar timestamp remains the left label. The `signal_delivery_audit.csv` records the delivery timestamp sidecar.
3. **Same-bar clean-validation exits are common in the 5m-only replay.** The 1m-fill validation routes those exits through the last 1m bar in the completed 5m bucket, but live execution still needs adapter-level proof of close-order timing and fill quality.
4. **Pyramid mode has no immediate server-side protective stop before the trail arms.** Risk is managed by close-back-into-range soft exits and EOD flattening until trail activation. That can be modeled, but it is not the same as broker-hosted protective OCO from entry.

## Verdict

NAS100 Scenario 0 is **reproducible and order-causal at 5m bar resolution**, and the most efficient frozen candidate now passes a stricter **5m-signal / 1m-fill** validation with point-in-time feature snapshots.

However, the strategy is **not yet live-equivalent**. Before calling it paper/live eligible, the next validation pass should use true broker tick/bid-ask quote history or a demo shadow feed, then compare expected fills, clean failures, soft exits, and trail/order refresh behavior against live-style execution reports.
