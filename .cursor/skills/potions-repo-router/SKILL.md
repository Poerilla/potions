---
name: potions-repo-router
description: >-
  Routes potions-repo tasks to the correct hub docs and domain skills.
  Use when the task is unfamiliar, the user asks where docs live, mentions
  Platform.md, STRATEGY_TRACKER, live/state vs live/demo, or needs task→doc
  routing before research, demos, plugins, causality, or backups.
---

# Potions repo router

Skills encode **workflow**. Hub docs encode **truth** (rankings, fill semantics, audit history). Prefer opening the hub over pasting long tables into chat.

## Path conventions

| Path | Use for |
|------|---------|
| `live/state/<slug>/` | Research/replay artifacts (`SUMMARY.md`, audits, equities, charts) |
| `live/demo/<run>/` | Continuous paper/OANDA daemons (pidfile, `PROGRESS.log`, fills) |
| `mnq/case_studies/STRATEGY_TRACKER.md` | Promotion / research rankings |
| `live/Platform.md` | Engine, broker, plugin contract, causality machinery |
| `live/CHANGE_LOG.md` | Dated runtime/research changes |
| `live/PROGRESS.log` | Append-only platform/research session notes |

## Task → doc matrix

| Task class | Read first | Then | Domain skill |
|------------|------------|------|--------------|
| Engine / broker / fills / plugin contract | [`live/Platform.md`](../../../live/Platform.md) | `live/specs/CAUSAL_*`, CHANGE_LOG | `potions-strategy-plugin`, `potions-causality-audit` |
| Rankings / promotion status | [`mnq/case_studies/STRATEGY_TRACKER.md`](../../../mnq/case_studies/STRATEGY_TRACKER.md) | study `SUMMARY.md`, CHANGE_LOG | `potions-tracker-docs` |
| Live / paper demo ops | [`live/demo/README.md`](../../../live/demo/README.md) | per-run `PROGRESS.log` / `run.log` | `potions-demo-status` |
| OANDA live vs sim trade tape | demo `fills.csv` + stored bars | fresh spawn `config_json` drift | `potions-oanda-live-sim-reconcile` |
| Month / rolling WR-PF filters | hub `FILTERS.md` + `live/asia_range_shadow.py` | plugin `skip_entry_months` / `shadow_roll_*` | `potions-quick-backtest` |
| Causality pass/fail | [`data/docs/AUDIT_TRACKER.md`](../../../data/docs/AUDIT_TRACKER.md) | Platform §7; master spec only if designing | `potions-causality-audit` |
| Quick / broker-like backtest | [`README.md`](../../../README.md) ranking layers | family driver + `live/state/<slug>/` | `potions-quick-backtest` |
| Batch finished / completion report | hub `RUN_COMPLETE.json` + `summary.csv` | `COMPLETION_REPORT.md` | `strategy-completion-report` |
| Per-instrument yearly / robustness / 50W-50L | state root `fills.csv` or `trades.csv` | hub `deep_check/` + `winloss_charts/` | `potions-instrument-deep-check` |
| Intraday condition / HTF / calendar lift profile | hub `SUMMARY.md` + `notables.csv` | research campaign tapes | `potions-intraday-condition-profile` |
| Futures HP size-up / 1.25× nulls / deployment tiers | [`live/state/futures_intraday_hp_live_plan/DEPLOYMENT_PLAN.md`](../../../live/state/futures_intraday_hp_live_plan/DEPLOYMENT_PLAN.md) | nulls `SUMMARY.md` + `COMPARISON.md` | `potions-futures-intraday-hp-sizeup` |
| Large data / Drive backup | [`scripts/LARGE_FILES_MANIFEST.md`](../../../scripts/LARGE_FILES_MANIFEST.md) | pack/unpack scripts | `potions-git-backup` |
| Workspace map | [`README.md`](../../../README.md) | tracker | — |

## When to open Platform.md

Open [`live/Platform.md`](../../../live/Platform.md) **before**:

- Changing fill semantics, slippage, OCO, gap-through, or `live_after_ts`
- Adding/changing `CausalityGuard` / feature snapshots
- Creating or promoting a Tier-1 `StrategyPlugin`
- Explaining engine ↔ plugin ↔ PaperBroker behavior
- Changing reported institutional metrics / scorecard hooks

**Same-PR rule:** fill/causality/metric/plugin-contract code changes **must** update Platform.md (Maintenance section). Use `potions-tracker-docs` for the full doc-sync checklist.

Do **not** use Platform.md for strategy rule definitions or leaderboard rankings — those stay in the tracker and study hubs.

## Related skills

- `potions-git-backup` — commit, pack, rclone
- `potions-demo-status` — morning live/demo check
- `potions-oanda-live-sim-reconcile` — live OANDA fills vs StrategyPlugin replay on demo bars
- `potions-strategy-plugin` — new plugin checklist
- `potions-quick-backtest` — replay entry points
- `potions-causality-audit` — lookahead / audit
- `potions-tracker-docs` — tracker / CHANGE_LOG / PROGRESS
- `strategy-completion-report` — headless completion report + email after batches
- `potions-instrument-deep-check` — yearly net/stress + robustness + win/loss charts
- `potions-intraday-condition-profile` — DOW / RSI / OBV / MA / ATR / range-half lift vs campaign tape
- `potions-futures-intraday-hp-sizeup` — futures 1.25× HP nulls, Tier A/B/C plan, size sensitivity
- `potions-job-email` — **always** email on replay/sweep/job complete or crash
