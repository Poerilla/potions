from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

from .store import FlatFileStore
from .models import utc_now_iso


POINT_VALUES: Dict[str, float] = {
    "MES": 5.0,
    "ES": 50.0,
    "MNQ": 2.0,
    "NQ": 20.0,
    "MYM": 0.5,
    "YM": 5.0,
}


def generate_market_close_report(store: FlatFileStore, report_date: str = "") -> str:
    store.ensure()
    report_date = report_date or datetime.utcnow().date().isoformat()
    strategy_rows = store.read_table("strategy_instances")
    strategy_state = store.read_table("strategy_state")
    positions = store.read_table("positions")
    orders = store.read_table("orders")
    intents = store.read_table("order_intents")
    fills = store.read_table("fills")
    alerts = store.read_table("alerts")
    jobs = store.read_table("jobs")
    levels = store.read_table("levels")
    verifications = store.read_table("pending_verifications")
    health = store.read_json("health.json") or {}

    open_orders = [o for o in orders if o.get("status") in {"submitted", "partially_filled"}]
    open_positions = [p for p in positions if int(float(p.get("quantity") or 0)) != 0]
    recent_fills = fills[-20:]
    risk_alerts = [a for a in alerts if a.get("level") in {"risk_block", "engine_error", "warning"}]
    engine_errors = [a for a in alerts if a.get("level") == "engine_error"]
    risk_blocks = [a for a in alerts if a.get("level") == "risk_block"]
    pending_verifications = [v for v in verifications if v.get("status") == "pending"]
    failed_jobs = [j for j in jobs if j.get("status") == "failed"]
    pending_jobs = [j for j in jobs if j.get("status") == "pending"]
    last_bar = str(health.get("last_bar", ""))
    latest_levels = _latest_levels(levels)
    broker_instruments = {row.get("strategy_id", ""): row.get("broker_instrument", "") for row in strategy_rows}
    positions_by_strategy = {
        (p.get("strategy_id", ""), p.get("instrument", ""), p.get("account_mode", "")): int(float(p.get("quantity") or 0))
        for p in positions
    }
    stale_expired = [
        o
        for o in open_orders
        if o.get("expires_after_ts") and last_bar and str(last_bar) > str(o.get("expires_after_ts"))
    ]
    pending_flatten_no_position = [
        o
        for o in open_orders
        if o.get("reduce_only") == "true"
        and o.get("order_type") == "market"
        and positions_by_strategy.get((o.get("strategy_id", ""), o.get("instrument", ""), o.get("account_mode", "")), 0) == 0
    ]
    unbracketed_entry_intents = [
        i
        for i in intents
        if i.get("status") in {"submitted", "created"}
        and i.get("reduce_only") != "true"
        and not i.get("bracket_stop_price")
    ]
    point_value = _point_value(strategy_rows)
    realized_points = sum(float(p.get("realized_pnl") or 0.0) for p in positions)
    realized_dollars = realized_points * point_value
    total_fills = len(fills)
    total_entry_fills = len([f for f in fills if f.get("reason") in {"entry", "runner_entry"}])
    total_exit_fills = total_fills - total_entry_fills
    open_order_counts = Counter(o.get("bracket_role") or o.get("order_type") for o in open_orders)
    verification_counts = Counter(v.get("status", "") for v in verifications)
    fill_counts = Counter(f.get("reason", "") for f in fills)

    lines: List[str] = [
        "# Market Close Report %s" % report_date,
        "",
        "Generated: `%s`" % utc_now_iso(),
        "State root: `%s`" % store.root,
        "Health status: `%s`" % health.get("status", "unknown"),
        "Last completed bar: `%s` `%s` `%s`" % (health.get("instrument", ""), health.get("timeframe", ""), last_bar),
        "",
        "## Live Ops Checklist",
        "",
        "| Status | Check | Detail |",
        "|---|---|---|",
    ]
    for status, check, detail in _ops_checks(
        strategy_rows=strategy_rows,
        open_orders=open_orders,
        open_positions=open_positions,
        pending_verifications=pending_verifications,
        stale_expired=stale_expired,
        pending_flatten_no_position=pending_flatten_no_position,
        unbracketed_entry_intents=unbracketed_entry_intents,
        failed_jobs=failed_jobs,
        engine_errors=engine_errors,
        risk_blocks=risk_blocks,
        health=health,
    ):
        lines.append("| %s | %s | %s |" % (status, check, detail))

    lines.extend(
        [
            "",
            "## Paper Replay Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Bars persisted | %d |" % _bar_count(store),
            "| Fills | %d |" % total_fills,
            "| Entry fills | %d |" % total_entry_fills,
            "| Exit fills | %d |" % total_exit_fills,
            "| Realized P/L, points | %.2f |" % realized_points,
            "| Point value used | $%.2f |" % point_value,
            "| Realized P/L, gross dollars | $%.2f |" % realized_dollars,
            "| Open positions | %d |" % len(open_positions),
            "| Open orders | %d |" % len(open_orders),
            "| Pending verifications | %d |" % len(pending_verifications),
            "| Risk blocks | %d |" % len(risk_blocks),
            "| Engine errors | %d |" % len(engine_errors),
            "",
            "Fill reasons: `%s`" % _counter_text(fill_counts),
            "",
            "Open order roles: `%s`" % _counter_text(open_order_counts),
            "",
            "Verification statuses: `%s`" % _counter_text(verification_counts),
            "",
        ]
    )

    lines.extend(
        [
            "## Strategy States",
            "",
        ]
    )
    if strategy_rows:
        lines.append("| Strategy | Type | Instrument | Broker Instrument | Mode | Enabled | Max Contracts | Max Orders |")
        lines.append("|---|---|---|---|---|---|---:|---:|")
        for row in strategy_rows:
            lines.append(
                "| {strategy_id} | {strategy_type} | {instrument} | {broker_instrument} | {account_mode} | {enabled} | {max_contracts} | {max_open_orders} |".format(**row)
            )
    else:
        lines.append("No strategy instances configured.")

    lines.extend(["", "## Active Levels", ""])
    if latest_levels:
        lines.append("| Strategy | Instrument | Level | Price | Active From |")
        lines.append("|---|---|---|---:|---|")
        for row in latest_levels:
            lines.append(
                "| {strategy_id} | {instrument} | {level_name} | {price} | {active_from} |".format(**row)
            )
    else:
        lines.append("No active levels.")

    lines.extend(["", "## Persisted Strategy State", ""])
    if strategy_state:
        lines.append("| Strategy | Summary |")
        lines.append("|---|---|")
        for row in strategy_state:
            lines.append("| %s | %s |" % (row.get("strategy_id", ""), _state_summary(row.get("state_json", ""))))
    else:
        lines.append("No strategy state persisted.")

    lines.extend(["", "## Open Positions", ""])
    if open_positions:
        lines.append("| Strategy | Instrument | Mode | Qty | Avg Price | Realized P/L Points | Gross $ |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for row in open_positions:
            gross = float(row.get("realized_pnl") or 0.0) * _instrument_point_value(row.get("instrument", ""))
            lines.append(
                "| {strategy_id} | {instrument} | {account_mode} | {quantity} | {avg_price} | {realized_pnl} | $%.2f |".format(**row)
                % gross
            )
    else:
        lines.append("No open positions.")

    lines.extend(["", "## Open Orders", ""])
    if open_orders:
        lines.append("| Order | Strategy | Trade | Side | Type | Qty | Limit | Stop | Role | Reduce Only | Live After | Expires | Note |")
        lines.append("|---|---|---|---|---|---:|---:|---:|---|---|---|---|---|")
        for row in open_orders:
            note = _order_note(row, last_bar, positions_by_strategy)
            lines.append(
                "| {broker_order_id} | {strategy_id} | {trade_id} | {side} | {order_type} | {remaining_quantity} | {limit_price} | {stop_price} | {bracket_role} | {reduce_only} | {live_after_ts} | {expires_after_ts} | ".format(**row)
                + note
                + " |"
            )
    else:
        lines.append("No open orders.")

    lines.extend(["", "## Verification Gate", ""])
    if verifications:
        lines.append("| Verification | Intent | Strategy | Mode | Status | Challenge | Created | Approved |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in verifications[-20:]:
            lines.append(
                "| {verification_id} | {intent_id} | {strategy_id} | {account_mode} | {status} | {challenge} | {created_at} | {approved_at} |".format(**row)
            )
    else:
        lines.append("No verification records.")

    lines.extend(["", "## Recent Fills", ""])
    if recent_fills:
        lines.append("| Time | Strategy | Trade | Side | Qty | Price | Reason |")
        lines.append("|---|---|---|---|---:|---:|---|")
        for row in recent_fills:
            lines.append("| {ts} | {strategy_id} | {trade_id} | {side} | {quantity} | {price} | {reason} |".format(**row))
    else:
        lines.append("No fills yet.")

    lines.extend(["", "## Exceptions / Risk Blocks", ""])
    if risk_alerts:
        lines.append("| Time | Strategy | Level | Message |")
        lines.append("|---|---|---|---|")
        for row in risk_alerts[-20:]:
            lines.append("| {created_at} | {strategy_id} | {level} | {message} |".format(**row))
    else:
        lines.append("No warnings or risk blocks.")

    lines.extend(["", "## Job Health", ""])
    lines.append("- Pending jobs: %d" % len(pending_jobs))
    lines.append("- Failed jobs: %d" % len(failed_jobs))
    lines.append("- Recovery files present: `%s`" % ", ".join(_recovery_files(store)))
    lines.append("- Next expected action: %s" % _next_expected_action(strategy_rows, latest_levels, open_orders, open_positions, last_bar))
    lines.extend(["", "## Live Credential Gate", ""])
    lines.append("- Tradovate routing remains disabled in v0; this report is paper-runtime only.")
    lines.append("- Before credentials: resolve broker-routable active contract, define roll policy, and run a paper replay on the same contract month path.")
    lines.append("- New live entries require 2FA; brackets, protective exits, cancels, and risk flatten orders do not.")
    lines.append("- Do not enable live mode while any checklist row is `BLOCK` or unexplained `WARN`.")

    text = "\n".join(lines) + "\n"
    path = store.reports_dir / ("%s.md" % report_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    store.write_json("health.json", {"status": "ok", "updated_at": utc_now_iso(), "last_report": str(path)})
    return text


def _ops_checks(
    strategy_rows: Sequence[Dict[str, str]],
    open_orders: Sequence[Dict[str, str]],
    open_positions: Sequence[Dict[str, str]],
    pending_verifications: Sequence[Dict[str, str]],
    stale_expired: Sequence[Dict[str, str]],
    pending_flatten_no_position: Sequence[Dict[str, str]],
    unbracketed_entry_intents: Sequence[Dict[str, str]],
    failed_jobs: Sequence[Dict[str, str]],
    engine_errors: Sequence[Dict[str, str]],
    risk_blocks: Sequence[Dict[str, str]],
    health: Dict[str, str],
) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    live_strategies = [s for s in strategy_rows if s.get("account_mode") == "live"]
    rows.append(("PASS" if not live_strategies else "WARN", "Account mode", "%d live strategy rows, %d paper strategy rows" % (len(live_strategies), len(strategy_rows) - len(live_strategies))))
    continuous = [s for s in strategy_rows if "CONT" in (s.get("broker_instrument", "").upper())]
    rows.append(("WARN" if continuous else "PASS", "Routable contract / roll", "Continuous placeholders: %s" % ", ".join(s.get("strategy_id", "") for s in continuous) if continuous else "Broker instruments are explicit"))
    rows.append(("PASS" if health.get("last_bar") else "WARN", "Market data replay", "Last completed bar: %s" % (health.get("last_bar") or "missing")))
    rows.append(("PASS" if not pending_verifications else "BLOCK", "2FA verification gate", "%d pending verification requests" % len(pending_verifications)))
    rows.append(("PASS" if not failed_jobs else "BLOCK", "Job queue", "%d failed jobs" % len(failed_jobs)))
    rows.append(("PASS" if not engine_errors else "BLOCK", "Engine errors", "%d engine errors" % len(engine_errors)))
    rows.append(("PASS" if not risk_blocks else "WARN", "Risk manager", "%d risk blocks" % len(risk_blocks)))
    rows.append(("PASS" if not stale_expired else "BLOCK", "Expired orders", "%d expired orders still open" % len(stale_expired)))
    rows.append(("PASS" if not unbracketed_entry_intents else "BLOCK", "Protective brackets", "%d open entry intents missing a bracket stop" % len(unbracketed_entry_intents)))
    rows.append(("INFO" if pending_flatten_no_position else "PASS", "Pending flatten orders", "%d reduce-only market orders have no matching position" % len(pending_flatten_no_position)))
    rows.append(("INFO" if open_positions else "PASS", "Open exposure", "%d open positions, %d open orders" % (len(open_positions), len(open_orders))))
    return rows


def _bar_count(store: FlatFileStore) -> int:
    n = 0
    for path in store.bars_dir.glob("*.csv"):
        try:
            with path.open("r", encoding="utf-8") as fh:
                n += max(sum(1 for _ in fh) - 1, 0)
        except FileNotFoundError:
            pass
    return n


def _latest_levels(levels: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    latest: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for row in levels:
        key = (row.get("strategy_id", ""), row.get("instrument", ""), row.get("level_name", ""))
        latest[key] = row
    return sorted(latest.values(), key=lambda r: (r.get("strategy_id", ""), r.get("level_name", "")))


def _state_summary(state_json: str) -> str:
    import json

    try:
        state = json.loads(state_json or "{}")
    except json.JSONDecodeError:
        return "invalid JSON"
    keys = [
        "year",
        "yor_high",
        "yor_low",
        "last_inside_swing_low",
        "last_inside_swing_high",
        "trade_seq",
        "active_trade_id",
        "active_direction",
        "full_tp_seen",
    ]
    parts = ["%s=%s" % (k, state.get(k, "")) for k in keys if k in state]
    return "`%s`" % "; ".join(parts)


def _instrument_point_value(instrument: str) -> float:
    return POINT_VALUES.get(str(instrument).upper(), 1.0)


def _point_value(strategy_rows: Sequence[Dict[str, str]]) -> float:
    if not strategy_rows:
        return 1.0
    return _instrument_point_value(strategy_rows[0].get("instrument", ""))


def _counter_text(counter: Counter) -> str:
    if not counter:
        return "none"
    return ", ".join("%s=%s" % (k or "blank", v) for k, v in sorted(counter.items()))


def _order_note(row: Dict[str, str], last_bar: str, positions_by_strategy: Dict[Tuple[str, str, str], int]) -> str:
    if row.get("expires_after_ts") and last_bar and str(last_bar) > str(row.get("expires_after_ts")):
        return "EXPIRED_STILL_OPEN"
    if row.get("reduce_only") == "true" and row.get("order_type") == "market":
        qty = positions_by_strategy.get((row.get("strategy_id", ""), row.get("instrument", ""), row.get("account_mode", "")), 0)
        if qty == 0:
            return "PENDING_FLATTEN_NO_POSITION"
        return "PENDING_FLATTEN_NEXT_BAR"
    if row.get("reduce_only") != "true" and not row.get("stop_price") and row.get("order_type") in {"limit", "stop"}:
        return "ENTRY_PARENT_BRACKET_ON_FILL"
    return ""


def _recovery_files(store: FlatFileStore) -> List[str]:
    names = []
    for rel in ["strategy_state.csv", "orders.csv", "positions.csv", "jobs.csv", "pending_verifications.csv", "health.json"]:
        if (store.root / rel).exists():
            names.append(rel)
    return names


def _next_expected_action(
    strategy_rows: Sequence[Dict[str, str]],
    latest_levels: Sequence[Dict[str, str]],
    open_orders: Sequence[Dict[str, str]],
    open_positions: Sequence[Dict[str, str]],
    last_bar: str,
) -> str:
    if open_positions:
        return "monitor protective exits and daily range-close conditions after the next completed bar"
    if open_orders:
        return "reconcile resting paper orders against the next completed tradable bar"
    if latest_levels:
        return "wait for the next completed bar and evaluate yearly ORB breakout/retest conditions"
    if strategy_rows:
        return "continue building opening range from completed Jan-Mar daily bars"
    return "configure at least one strategy instance"
