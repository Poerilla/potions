"""NQ v2b S_1_1_3 gated by monthly-open extension band fade touch.

Instead of fading the pct75 band directly: wait until price **trades through**
the band entry (gap-through voids), then allow v2b ``S_1_1_3`` for the rest of
that calendar month — either **with** fade (``aligned``) or **against** fade
(``opposed``):

  aligned: touch lower → Long v2b; touch upper → Short v2b
  opposed: touch lower → Short v2b; touch upper → Long v2b

Implemented via ``prior_aligned_only`` / ``prior_opposite_only`` + band-touch
events expanded onto subsequent RTH sessions in the month.

Hub: ``live/state/nq_v2b_mo_ext_band_fade_gate/`` (aligned) or ``…_fade_opposed/``
DSR: TRL-2026-00125 (aligned) / TRL-2026-00126 (opposed)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import traceback
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .monthly_atr4_helpers import load_1h
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    build_month_plans,
)
from .notify_email import send_email
from .nq_v2b_prior_opposed_replay import BOOK_SPECS
from .quarterly_atr4_fade_broker import MARKETS as MO_MARKETS
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run, metrics_from_equity_curve
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, _rth_bars, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT_ALIGNED = REPO / "live" / "state" / "nq_v2b_mo_ext_band_fade_gate"
DEFAULT_OUT_OPPOSED = REPO / "live" / "state" / "nq_v2b_mo_ext_band_fade_opposed"
NY = "America/New_York"
FEE = 1.50
DSR_ALIGNED = "TRL-2026-00125"
DSR_OPPOSED = "TRL-2026-00126"


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _gapped_through(side: str, entry: float, prev_close: float, bar_open: float) -> bool:
    if side == "long":
        return prev_close > entry and bar_open < entry
    return prev_close < entry and bar_open > entry


def _touched(side: str, entry: float, bar_high: float, bar_low: float) -> bool:
    return bar_low <= entry <= bar_high


def collect_band_touches(
    *,
    month_plans: Dict[str, dict],
    bars_1h: pd.DataFrame,
    require_trade_through: bool = True,
) -> List[Dict[str, Any]]:
    """Return first trade-through touch per side per month on 1h bars."""
    touches: List[Dict[str, Any]] = []
    done: Dict[Tuple[str, str], bool] = {}
    prev_close: Optional[float] = None
    bars = bars_1h.sort_index()
    for ts, row in bars.iterrows():
        ts_utc = pd.Timestamp(ts)
        if ts_utc.tzinfo is None:
            ts_utc = ts_utc.tz_localize("UTC")
        ny = ts_utc.tz_convert(NY)
        month_key = "%04d-%02d" % (int(ny.year), int(ny.month))
        plan = month_plans.get(month_key) or {}
        if not plan:
            prev_close = float(row["close"])
            continue
        watch = str(plan.get("watch_start_ts") or "")
        mend = str(plan.get("month_end_ts") or "")
        ts_s = ts_utc.tz_convert("UTC").isoformat().replace("+00:00", "Z")
        if watch and ts_s < watch:
            prev_close = float(row["close"])
            continue
        if mend and ts_s >= mend:
            prev_close = float(row["close"])
            continue
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        for side_key, fade_side in (("long", "long"), ("short", "short")):
            leg = plan.get(side_key)
            if not leg or done.get((month_key, fade_side)):
                continue
            entry = float(leg["entry"])
            if require_trade_through and prev_close is not None:
                if _gapped_through(side_key, entry, prev_close, o):
                    continue
            if not _touched(side_key, entry, h, l):
                continue
            done[(month_key, fade_side)] = True
            touches.append(
                {
                    "ts": ts_s,
                    "available_at_ts": ts_s,
                    "side": fade_side,
                    "month_key": month_key,
                    "entry": entry,
                    "source": "mo_ext_band_touch",
                }
            )
        prev_close = c
    return touches


def expand_touches_to_session_events(
    touches: Sequence[Dict[str, Any]],
    regime_dates: Sequence[date],
) -> Dict[str, List[Dict[str, str]]]:
    """Propagate month band-touch gates onto later RTH sessions in that month."""
    by_month: Dict[str, List[Dict[str, Any]]] = {}
    for t in touches:
        by_month.setdefault(str(t["month_key"]), []).append(t)

    events: Dict[str, List[Dict[str, str]]] = {}
    for d in regime_dates:
        month_key = "%04d-%02d" % (d.year, d.month)
        month_touches = by_month.get(month_key) or []
        if not month_touches:
            continue
        session_open = pd.Timestamp(datetime.combine(d, time(9, 30)), tz=NY).tz_convert("UTC")
        for touch in month_touches:
            touch_ts = pd.Timestamp(touch["ts"])
            if touch_ts.tzinfo is None:
                touch_ts = touch_ts.tz_localize("UTC")
            touch_ny = touch_ts.tz_convert(NY).date()
            if touch_ny > d:
                continue
            if touch_ny == d:
                avail = touch_ts
            else:
                avail = session_open
            avail_s = avail.tz_convert("UTC").isoformat().replace("+00:00", "Z")
            events.setdefault(d.isoformat(), []).append(
                {
                    "ts": avail_s,
                    "available_at_ts": avail_s,
                    "side": str(touch["side"]),
                    "source": "mo_ext_band_touch",
                    "month_key": month_key,
                }
            )
    return events


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = _rth_bars(raw_day, session)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run(
    *,
    output_root: Path,
    market: str = "nq",
    book: str = "S_1_1_3",
    start: date = date(2021, 3, 4),
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    force: bool = True,
    email: bool = False,
    require_trade_through: bool = True,
    gate_mode: str = "aligned",
) -> int:
    """``gate_mode``: ``aligned`` = v2b with fade; ``opposed`` = v2b against fade."""
    market = market.lower()
    gate_mode = str(gate_mode or "aligned").strip().lower()
    if gate_mode not in {"aligned", "opposed"}:
        raise ValueError("gate_mode must be aligned|opposed")
    opposed = gate_mode == "opposed"
    dsr = DSR_OPPOSED if opposed else DSR_ALIGNED
    gate_name = "mo_ext_band_touch_fade_opposed" if opposed else "mo_ext_band_touch_fade_aligned"
    if book not in BOOK_SPECS:
        raise ValueError("book must be one of %s" % list(BOOK_SPECS))
    cfg = MARKETS[market]
    instrument = cfg.instrument
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    entry_qty, tp1_qty, tp2_qty, targeted_runner_qty, runner_target_r_mult = BOOK_SPECS[book]
    strategy_id = "%s_v2b_mo_ext_band_fade_%s_%s" % (market, gate_mode, book)
    state_root = output_root / "states" / strategy_id

    write_run_manifest(
        output_root,
        data_inputs=[cfg.dbn_path, MO_MARKETS["NQ"].csv],
        strategy_config={
            "strategy_type": "v2b_scaleout",
            "book": book,
            "gate": gate_name,
            "gate_mode": gate_mode,
            "entry_mode": "pct75",
            "rolling_window": rolling_window,
            "require_trade_through": require_trade_through,
            "dsr_trial_id": dsr,
            "start": start.isoformat(),
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE},
        extra={"notes": "band touch gates v2b %s fade direction" % gate_mode},
    )

    _progress(output_root, "Building month plans (pct75)...")
    mo_spec = MO_MARKETS["NQ"]
    month_plans = build_month_plans(
        mo_spec,
        entry_mode="pct75",
        sl_mode="wide_2.5x",
        rolling_window=rolling_window,
    )
    (output_root / "month_plans.json").write_text(
        json.dumps(month_plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    _progress(output_root, "Scanning 1h bars for band touches...")
    bars_1h = load_1h(mo_spec)
    touches = collect_band_touches(
        month_plans=month_plans,
        bars_1h=bars_1h,
        require_trade_through=require_trade_through,
    )
    (output_root / "band_touches.json").write_text(
        json.dumps(touches, indent=2) + "\n", encoding="utf-8"
    )
    _progress(
        output_root,
        "Band touches: %d (long=%d short=%d)"
        % (
            len(touches),
            sum(1 for t in touches if t["side"] == "long"),
            sum(1 for t in touches if t["side"] == "short"),
        ),
    )

    _progress(output_root, "Loading %s 1m bars..." % instrument)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    gate_events = expand_touches_to_session_events(touches, regime_dates)
    n_ev = sum(len(v) for v in gate_events.values())
    _progress(
        output_root,
        "Expanded gate events: %d across %d sessions (regime=%d)"
        % (n_ev, len(gate_events), len(regime_dates)),
    )
    (output_root / "gate_events_meta.json").write_text(
        json.dumps(
            {
                "n_touches": len(touches),
                "n_session_events": n_ev,
                "n_sessions_with_gate": len(gate_events),
                "n_regime_sessions": len(regime_dates),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    strategy_config: Dict[str, Any] = {
        "market": market,
        "mode": "oco_then_reverse",
        "entry_qty": int(entry_qty),
        "tp1_qty": int(tp1_qty),
        "tp2_qty": int(tp2_qty),
        "tick_size": 0.25,
        "use_regime_filter": True,
        "start": start.isoformat(),
        "regime_dates": [d.isoformat() for d in regime_dates],
        "record_levels": False,
        "dynamic_sizing_events": gate_events,
        "prior_opposite_only": bool(opposed),
        "prior_aligned_only": not bool(opposed),
        "book": book,
        "gate": gate_name,
    }
    if opposed:
        strategy_config.update(
            {
                "prior_opposite_entry_qty": int(entry_qty),
                "prior_opposite_tp1_qty": int(tp1_qty),
                "prior_opposite_tp2_qty": int(tp2_qty),
            }
        )
    if targeted_runner_qty is not None:
        strategy_config["targeted_runner_qty"] = int(targeted_runner_qty)
    if runner_target_r_mult is not None:
        strategy_config["runner_target_r_mult"] = float(runner_target_r_mult)

    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2b_scaleout",
                    version="v1",
                    instrument=instrument,
                    broker_instrument=instrument,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=int(entry_qty),
                    max_open_orders=64,
                    config_json=json.dumps(strategy_config, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0),
    )
    audit_bars: List[AuditBar] = []
    _progress(output_root, "Replaying %d RTH sessions..." % len(regime_dates))
    for idx, day in enumerate(regime_dates, start=1):
        df = _rth_bars(gby.get(day), day)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=instrument,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(cfg.dbn_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 250 == 0:
            _progress(output_root, "  %d/%d sessions" % (idx, len(regime_dates)))
    store.flush_tables()

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=instrument,
        fee_per_unit=FEE,
    )
    net = float(audit["net_usd"])
    stress = float(audit["intrabar_stress_dd_usd"])
    ns = net / abs(stress) if abs(stress) > 1e-9 else 0.0
    trade_ids = sorted({u.trade_id for u in units})
    from .replay_audit import POINT_VALUES

    point_value = float(POINT_VALUES.get(instrument.upper(), 20.0))
    wins_by_trade = 0
    for tid in trade_ids:
        pnl = sum((u.points * point_value - FEE) for u in units if u.trade_id == tid)
        if pnl > 0:
            wins_by_trade += 1
    win_rate = 100.0 * wins_by_trade / len(trade_ids) if trade_ids else 0.0

    # Validate gate: aligned → same side event; opposed → opposite side event
    fills = pd.read_csv(state_root / "fills.csv") if (state_root / "fills.csv").exists() else pd.DataFrame()
    violations = 0
    aligned = 0
    if not fills.empty:
        ents = fills[(fills["strategy_id"].astype(str) == strategy_id) & (fills["reason"] == "entry")]
        for _, row in ents.iterrows():
            entry_ts = pd.Timestamp(row["ts"])
            if entry_ts.tzinfo is None:
                entry_ts = entry_ts.tz_localize("UTC")
            session = entry_ts.tz_convert(NY).date().isoformat()
            v2b_side = "long" if str(row["side"]).lower() == "buy" else "short"
            want = ("short" if v2b_side == "long" else "long") if opposed else v2b_side
            ok = False
            for ev in gate_events.get(session, []):
                ev_ts = pd.Timestamp(ev.get("available_at_ts") or ev["ts"])
                if ev_ts.tzinfo is None:
                    ev_ts = ev_ts.tz_localize("UTC")
                if str(ev.get("side")).lower() == want and ev_ts < entry_ts:
                    ok = True
                    break
            if ok:
                aligned += 1
            else:
                violations += 1

    metrics = {
        "strategy_id": strategy_id,
        "book": book,
        "trades": len(trade_ids),
        "units": len(units),
        "net_usd": net,
        "stress_dd": stress,
        "close_dd": float(audit.get("closed_dd_usd") or 0.0),
        "ns": ns,
        "win_rate_pct": win_rate,
        "band_touches": len(touches),
        "gate_sessions": len(gate_events),
        "aligned_entries": aligned,
        "causality_violations": violations,
        "regime_sessions": len(regime_dates),
    }
    (output_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Write a simple equity via audit helper path if present
    eq_path = state_root / "equity_curve.csv"
    risk = {}
    if eq_path.exists():
        risk = metrics_from_equity_curve(eq_path)

    lines = [
        "# NQ v2b S_1_1_3 — monthly ext-band fade %s gate" % gate_mode,
        "",
        "Gate: price must **trade through** pct75 band entry (gap-through void). "
        + (
            "Then v2b ``S_1_1_3`` may fire only **opposite** the fade direction for the rest of the month."
            if opposed
            else "Then v2b ``S_1_1_3`` may fire only in the **fade direction** for the rest of the month."
        ),
        "",
        f"- DSR: `{dsr}`",
        f"- Gate mode: **{gate_mode}**",
        f"- Start: **{start.isoformat()}** · regime sessions: **{len(regime_dates)}**",
        f"- Band touches: **{len(touches)}** (long {sum(1 for t in touches if t['side']=='long')} / "
        f"short {sum(1 for t in touches if t['side']=='short')})",
        f"- Sessions with active gate: **{len(gate_events)}**",
        "",
        "## Results",
        "",
        f"| Trades | Units | Net $ | Stress DD | N/S | Win% | Gate OK | Violations |",
        f"|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {metrics['trades']} | {metrics['units']} | {net:,.0f} | {stress:,.0f} | {ns:.2f} | "
        f"{metrics['win_rate_pct']:.1f} | {aligned} | {violations} |",
        "",
        "Sibling: aligned hub `live/state/nq_v2b_mo_ext_band_fade_gate/` · "
        "ST prior-opposed resting_limit ≈ N/S **19.56**.",
        "",
        "Stance: research.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email_body = "\n".join(
        [
            "potions: NQ v2b mo-ext band fade %s gate (S_1_1_3)" % gate_mode,
            "",
            "Hub: %s" % output_root,
            "DSR: %s" % dsr,
            "",
            "Trades=%d net=$%s stress=$%s N/S=%.2f win%%=%.1f gate_ok=%d violations=%d"
            % (
                metrics["trades"],
                "{:,.0f}".format(net),
                "{:,.0f}".format(abs(stress)),
                ns,
                metrics["win_rate_pct"],
                aligned,
                violations,
            ),
            "Band touches=%d · gate sessions=%d" % (len(touches), len(gate_events)),
            "",
            "Stance: research.",
        ]
    )
    (output_root / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(metrics.keys()))
        w.writeheader()
        w.writerow(metrics)
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "dsr": dsr, "gate_mode": gate_mode, "metrics": metrics}, indent=2) + "\n",
        encoding="utf-8",
    )

    log_run(
        run_class="broker_like",
        variant_slug=strategy_id,
        instrument=instrument.upper(),
        hub_path=str(output_root.relative_to(REPO)),
        net_usd=net,
        stress_dd_usd=stress,
        close_mtm_dd_usd=metrics["close_dd"],
        ns=ns,
        trades=int(metrics["trades"]),
        units=int(metrics["units"]),
        dsr_trial_id=dsr,
        meta={
            "book": book,
            "gate": gate_name,
            "gate_mode": gate_mode,
            "band_touches": len(touches),
            "violations": violations,
            **risk,
        },
        notes="nq_v2b_mo_ext_band_gate_replay",
    )
    _progress(output_root, "DONE net=%+.0f N/S=%.2f trades=%d" % (net, ns, metrics["trades"]))
    if email:
        send_email(
            subject="potions: NQ v2b mo-ext band fade %s gate (S_1_1_3)" % gate_mode,
            body=email_body,
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate-mode", default="aligned", choices=("aligned", "opposed"))
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--market", default="nq")
    ap.add_argument("--book", default="S_1_1_3", choices=list(BOOK_SPECS))
    ap.add_argument("--start", default="2021-03-04")
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--allow-gap-fills", action="store_true", help="Disable trade-through requirement")
    args = ap.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    if out is None:
        out = DEFAULT_OUT_OPPOSED if args.gate_mode == "opposed" else DEFAULT_OUT_ALIGNED
    try:
        return run(
            output_root=out,
            market=str(args.market),
            book=str(args.book),
            start=date.fromisoformat(str(args.start)),
            rolling_window=int(args.rolling_window),
            force=not bool(args.no_force),
            email=bool(args.email),
            require_trade_through=not bool(args.allow_gap_fills),
            gate_mode=str(args.gate_mode),
        )
    except Exception:
        err = traceback.format_exc()
        hub = out
        hub.mkdir(parents=True, exist_ok=True)
        (hub / "EMAIL.txt").write_text("FAILED\n\n%s\n" % err, encoding="utf-8")
        if args.email:
            send_email(subject="potions: NQ v2b mo-ext band fade gate FAILED", body=(hub / "EMAIL.txt").read_text())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
