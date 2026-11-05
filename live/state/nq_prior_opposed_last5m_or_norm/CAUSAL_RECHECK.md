# NQ Prior-Opposed — Causal Recheck (deployable-to-demo confirmation)

**Tape:** `nq_v2b_prior_opposed_stpmc_resting_limit_through_20261011` (gate_mode=resting_limit, book S_1_1_3), rebuilt on the new 1m data through 2026-10-11.
**Question:** Is every entry condition — the prior-opposed ST+PMC gate, the normal-range (or_norm) bucket, and the opening range — knowable *strictly before* the trade is placed?

## Result: PASS — all gates causal

| Gate | Check | Result |
|---|---|---|
| Replay guard | `causality_violations.csv` rows | **0** |
| Entry fill timing | filled entry strictly after the entry intent `live_after_ts` (confirming bar) | **484 / 484** |
| ST+PMC prior-opposed | `v2b_entry_gate` snapshots whose `prior_event.available_at_ts` ≤ arm bar | **1114 / 1114** (0 violations) |
| Opening range | `v2b_opening_range` snapshots `or_finalized` before arm | **297,647 / 297,647** |
| Normal-range (or_norm) | or_norm entries before 09:45 (OR window 09:30–09:45 incomplete) | **0** (earliest entry 09:45:00) |

## Why each condition is causal

1. **Prior-opposed ST+PMC gate.** The opposite-side ST entry is a *resting limit* whose availability stamp is `live_after_ts + 1h` — the completed hourly bar, not the left-label wall clock. Every entry-gate snapshot that referenced a prior opposite event carried `prior_event.available_at_ts ≤ current_bar_ts`, and `source = st_resting_limit_hour_complete`. No gate was read before its hour closed.
2. **Normal-range (or_norm) bucket.** The bucket ranks the current session's opening-range width (09:30–09:45) against the trailing 60 sessions. The current OR is only fully formed at 09:45, and no or_norm campaign enters before 09:45:00 — so the label is known before the first fill, using only the current + prior complete windows.
3. **Opening range / v2b arm.** The 15-bar OR finalizes at the 09:44 left-label bar (09:45:00 close) before the entry stop arms; 100% of snapshots show `or_finalized=True` at/before arm.
4. **Fill guard.** Every filled entry (484/484) fills on a bar strictly after its intent `live_after_ts`; the broker `live_after_ts` guard (CO2b) holds. The engine wrote zero causality violations.

## Verdict

The prior-opposed edge on the refreshed tape (484 campaigns, $1,266,970 net, N/S 10.06, last fill 2026-10-08) uses only pre-trade-knowable information for the gate, the regime (or_norm), and the opening range. **Deployable-to-demo edge is confirmed causal** at 1m / hour-complete resolution. Remaining caveat (unchanged): this proves ordering at 1m/hour-complete resolution, not sub-second broker queue placement — same-minute arm→fill campaigns still warrant tick/broker-paper parity if promoted past demo.
