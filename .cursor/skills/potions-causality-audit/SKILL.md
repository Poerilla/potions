---
name: potions-causality-audit
description: >-
  Runs potions causality and lookahead audits for StrategyPlugin replays.
  Use when checking live_after_ts, feature snapshots, CausalityGuard,
  resting-limit gates, broker realism known-answers, or AUDIT_TRACKER pass/fail.
---

# Causality / lookahead audits

## Read order

1. [`live/Platform.md`](../../../live/Platform.md) **§7** (and §6 for `live_after_ts` / stop-first)
2. Pass/fail control: [`data/docs/AUDIT_TRACKER.md`](../../../data/docs/AUDIT_TRACKER.md)
3. Deep design only if inventing new validation: [`live/specs/CAUSAL_VALIDATION_MASTER_SPEC.md`](../../../live/specs/CAUSAL_VALIDATION_MASTER_SPEC.md)
4. Mechanism falsification (Tier-1): [`live/specs/CAUSAL_GRAPH.md`](../../../live/specs/CAUSAL_GRAPH.md)

Code: [`live/causality.py`](../../../live/causality.py) (`CausalityGuard`).

## Checklist

- [ ] Intents set `live_after_ts` to confirming bar ts; fills only when `bar.ts` **strictly after**
- [ ] Features: `event_ts <= available_at_ts <= current_bar_ts`
- [ ] HTF gates use **bar-complete** availability (left-labeled hour → `live_after_ts + 1h`), not raw left-label as wall clock
- [ ] Replay emits `feature_snapshots.csv` when Tier-1; `causality_violations.csv` header-only if clean
- [ ] Campaign gate audit (prior-opposed): prerequisite event `event_ts < entry_ts` same session
- [ ] Promotion standard for delayed-arming family: **resting-limit hour-complete** (`gate_mode=resting_limit`)
- [ ] Log DSR trial row **before** peeking at results (`data/validation/dsr_trial_ledger.csv`)
- [ ] Update AUDIT_TRACKER row + link artifacts

## Known-answer / scrutiny drivers

| Driver | Role |
|--------|------|
| `live/broker_realism_validation.py` | Fill realism known-answers + charts |
| `live/v2b_prior_opposed_execution_scrutiny.py` | Timing / same-bar ambiguity / latency |
| `live/tests/test_institutional_hardening.py` | Guard / manifest tests |

Example SOLID review path: study `LOOKAHEAD_REVIEW.md` under resting-limit state hubs.

## After audit

- Pass + promotion narrative → `potions-tracker-docs`
- Contract/fill/guard code change → update Platform.md **same PR**

## Related skills

- `potions-strategy-plugin` — emit causal intents correctly
- `potions-quick-backtest` — regenerate states under audit
- `potions-tracker-docs` — record pass/fail in tracker/CHANGE_LOG
- `potions-repo-router` — when to open Platform vs master spec
