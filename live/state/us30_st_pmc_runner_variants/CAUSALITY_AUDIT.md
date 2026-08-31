# US30 ST+PMC Causality And 1m Fill Audit

**Scope:** US30 ST+PMC fair 3R and runner variants in this hub.

**Conclusion:** PASS

The replay now treats left-labeled hourly candles as completed one hour later. Signals are processed with `broker_fills=False`; fills are accepted only from the 1m tape.

## Performance Impact

The previous positive US30 3R baseline does **not** survive completed-hour causality. The stronger audit demotes the fair 3R control from a marketable baseline to a rejected/diagnostic row. The finite 2R->10R runner remains historically positive, but much weaker than the pre-fix/stale lot-correct snapshot.

| Variant | Net | Stress DD | N/S | Units | Max open | Current read |
|---|---:|---:|---:|---:|---:|---|
| `sl50_tp150_3r_1mfill` | -$982 | -$4,599 | -0.21 | 1,017 | 1 | Causal but no longer positive; do not market as baseline. |
| `sl50_tp150_runners_2r_10r` | $13,340 | -$9,066 | 1.47 | 1,908 | 3 | Causal positive research row; modest, not a promotion-quality headline. |
| `sl50_tp150_runners_2r_indef` | $9,164 forced-flat | -$34,332 | 0.27 | 3,051 | 77 | Causal inventory sleeve only; not rankable against flat books. |

## Variant Audit Table

| Variant | Fills | Entry fills | Feature snapshots | Causal rows | Feature order fails | Missing 1m | live_after fails | Touch fails | Min entry delay (s) | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `sl50_tp150_3r_1mfill` | 2034 | 1017 | 142887 | 0 | 0 | 0 | 0 | 0 | 60.0 | **PASS** |
| `sl50_tp150_runners_2r_10r` | 3816 | 1908 | 127536 | 0 | 0 | 0 | 0 | 0 | 60.0 | **PASS** |
| `sl50_tp150_runners_2r_indef` | 6020 | 3051 | 142904 | 0 | 0 | 0 | 0 | 0 | 60.0 | **PASS** |

## Interpretation

- `causality_violation_rows=0` means the engine-level `CausalityGuard` did not record feature/order causality errors.
- `feature_order_fails=0` means every snapshot satisfied `event_ts <= available_at_ts <= current_bar_ts`.
- `live_after_fails=0` means no fill occurred at or before the order's activation timestamp.
- `missing_1m=0` and `touch_fails=0` mean every fill timestamp exists on the 1m source tape and the bar supports the fill type/price.
- A low `min_entry_delay_seconds` is acceptable only if it is positive; it means price touched soon after a completed-hour signal, not before it.
