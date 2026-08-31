# LOOKAHEAD_REVIEW — CHOP20 causal entry variants

**Status:** PASS

## Contract

1. Daily CHOP20 + close breakout known at `daily_feature_available_at` (last RTH 1m).
2. Entry fill strictly **after** availability (`close_to_globex` or `close_to_next_rth`).
3. Management only on bars after `entry_ts`; stop-first.
4. Range confirm ≤ signal day; age ≤ 60.

## Checks

| slug | trades | avail<entry | exit>entry | confirm | age | mode | Pass |
|---|---:|---:|---:|---:|---:|---:|---|
| mnq__close_to_globex__baseline | 30 | 30 | 30 | 30 | 30 | 30 | PASS |
| mnq__close_to_globex__hp_wom3 | 13 | 13 | 13 | 13 | 13 | 13 | PASS |
| mnq__close_to_next_rth__baseline | 27 | 27 | 27 | 27 | 27 | 27 | PASS |
| mnq__close_to_next_rth__hp_wom3 | 13 | 13 | 13 | 13 | 13 | 13 | PASS |
| nq__close_to_globex__baseline | 79 | 79 | 79 | 79 | 79 | 79 | PASS |
| nq__close_to_globex__hp_rsi_gt70 | 29 | 29 | 29 | 29 | 29 | 29 | PASS |
| nq__close_to_globex__hp_rsi_with_side | 67 | 67 | 67 | 67 | 67 | 67 | PASS |
| nq__close_to_next_rth__baseline | 67 | 67 | 67 | 67 | 67 | 67 | PASS |
| nq__close_to_next_rth__hp_rsi_gt70 | 28 | 28 | 28 | 28 | 28 | 28 | PASS |
| nq__close_to_next_rth__hp_rsi_with_side | 60 | 60 | 60 | 60 | 60 | 60 | PASS |

## Residual

- Still pandas path — StrategyPlugin `live_after_ts` / feature_snapshots required for Tier-1.
- Tick path inside 1m bar unknown; stop-first is pessimistic.

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_causal_entry_audit`
Source: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_causal_entry_variants`
DSR: `TRL-2026-00181`
