# Potions Cursor skills

Project skills for agents working in this repo. **Skills encode workflow; hub docs encode truth.**

Location: `.cursor/skills/<name>/SKILL.md` (auto-discovered; no `disable-model-invocation`).

| Skill | Use for |
|-------|---------|
| [potions-repo-router](potions-repo-router/SKILL.md) | Task → doc routing; when to open Platform.md |
| [potions-git-backup](potions-git-backup/SKILL.md) | Git check-in, large-file pack/unpack, rclone Drive |
| [potions-demo-status](potions-demo-status/SKILL.md) | Live/demo paper & OANDA morning status |
| [potions-oanda-reconcile](potions-oanda-reconcile/SKILL.md) | Query OANDA practice; repair local demo positions |
| [potions-strategy-plugin](potions-strategy-plugin/SKILL.md) | New StrategyPlugin + registry |
| [potions-quick-backtest](potions-quick-backtest/SKILL.md) | Broker-like / quick replays |
| [potions-causality-audit](potions-causality-audit/SKILL.md) | Causality / lookahead / AUDIT_TRACKER |
| [potions-tracker-docs](potions-tracker-docs/SKILL.md) | STRATEGY_TRACKER, CHANGE_LOG, PROGRESS, Platform sync |
| [strategy-completion-report](strategy-completion-report/SKILL.md) | Post-batch completion report + phone email; headless `agent -p` |

## Hub docs (do not duplicate into skills)

- [`README.md`](../../README.md) — workspace map
- [`mnq/case_studies/STRATEGY_TRACKER.md`](../../mnq/case_studies/STRATEGY_TRACKER.md) — rankings
- [`live/Platform.md`](../../live/Platform.md) — platform machinery
- [`live/CHANGE_LOG.md`](../../live/CHANGE_LOG.md) — dated changes
- [`live/demo/README.md`](../../live/demo/README.md) — demo ops
- [`data/docs/AUDIT_TRACKER.md`](../../data/docs/AUDIT_TRACKER.md) — audit pass/fail
- [`scripts/LARGE_FILES_MANIFEST.md`](../../scripts/LARGE_FILES_MANIFEST.md) — archive policy
