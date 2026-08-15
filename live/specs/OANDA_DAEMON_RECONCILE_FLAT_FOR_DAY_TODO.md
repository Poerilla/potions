# OANDA strategy-daemon periodic reconcile + flatten-for-day

Status: **IMPLEMENTED (shadow-first)** — 2026-08-15.  
Live enforce: set `POTIONS_OANDA_CONTAINMENT=live` (default remains `shadow`).

## Goal

Each OANDA strategy daemon owns its **state-mismatch risk**. Controllers under
`live/demo/oanda_daemon_reconcile.py` run a **~2m bracket watchdog** and a
**15m hard reconcile**. Soft drift adopts broker truth; hard mismatch /
ambiguous ownership → **FLAT_FOR_DAY** (live mode) or would-action logs (shadow).

This is separate from:

- one-shot ops sync (`potions-oanda-reconcile` / `oanda-practice-sync`)
- live↔sim trade-tape checks (`potions-oanda-live-sim-reconcile`)
- risk-guard MAE / avg-loss shadow (`live/risk_guard_shadow.py`)

## Policy (shipped)

| Cadence | Action |
|---------|--------|
| ~2m watchdog | Bracket invariant on local focus book (stop coverage, stop-only, orphans) |
| Every 15m | Account details → owned qty vs local; soft adopt or hard mismatch |
| Match / soft drift | `reconcile_from_account_details` (tag-scoped) |
| Ownership certain + missing brackets | Freeze entries (`RuntimeSupervisor` ENTRY_FROZEN) |
| Hard mismatch / foreign bleed | Cancel owned rests, `go_flat(focus)`, write `state/FLAT_FOR_DAY.json`, supervisor `flat_for_day` |
| NY session roll | Clear FLAT_FOR_DAY when flag `session_date` < today |

### Flat-for-day semantics

1. Cancel working entry / OCO legs owned by this strategy tag.
2. Market-close focus instrument via `OandaBroker.go_flat`.
3. Persist `state/FLAT_FOR_DAY.json` + `daemon_strategy_state.json`.
4. Supervisor blocks new non-reduce entries until day roll / clear.
5. Append `reconciliation_events` + optional Resend alert.

Do **not** wipe historical `fills.csv`. Do **not** flatten sibling strategies.

## Wired runners

- `live/demo/oanda_v2b_ungated_common.py` — NAS100/SPX500 (and other) v2b OANDA demos:
  `RuntimeSupervisor` on broker, `DaemonContainmentController` on bootstrap + poll loop.
- Monday OR OANDA (`usdjpy_monday_or_ungated_oanda.py`, `us30_monday_or_oanda.py`) and
  hourly ST+PMC OANDA runners — same helpers via `install_containment` /
  `oanda_broker_with_supervisor`.
- Asia-range London (`usdjpy_asia_range_london_common.py`) and US30 London prior-opposed
  (`us30_london_prior_opposed_common.py`) — same controller when `oanda_routing=True`.

## Curated fault fixtures + bar-day harness

`live/tests/fixtures/oanda_faults/` — reconstructed Aug 13–14 incidents (stop-only,
orphan protective, open-without-brackets, foreign bleed, qty mismatch, stream-hung
missed entry) plus a healthy book. Incident days include **real OANDA demo 1m bar
slices** under each book’s `bars/`.

Offline harness: `python -m potions.live.demo.oanda_fault_replay` (optionally
`--also-plugin-replay --hub live/state/oanda_fault_replay_curated --email`).
Tests: `live/tests/test_oanda_daemon_containment.py`,
`live/tests/test_oanda_fault_day_replay.py`.

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `POTIONS_OANDA_CONTAINMENT` | `shadow` | `shadow` = detect/log/email would-actions; `live` = freeze/flatten |

## Acceptance

- [x] Injected stop-only / orphan / opposite-qty fixtures classified correctly.
- [x] Live mode sets FLAT_FOR_DAY / ENTRY_FROZEN without clearing on `mark_reconciled`.
- [x] Shadow mode does not mutate supervisor.
- [x] Fault-day harness replays Aug 13–14 bar slices + books → expected containment.
- [x] Stream-staleness (≥180s) freezes entries; reconnect REST-reconciles then rearms.
- [x] Wire Monday OR / ST+PMC runners to the same controller.
- [x] Wire asia-range / London prior-opposed commons the same way.
- [ ] ≥1 week shadow on practice daemons before enabling `live` flatten.
- [ ] Optional: account-level rate-limit coordinator across sibling daemons.
