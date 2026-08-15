"""London-session v2b S_1_1_3 with ST+PMC prior-opposed or prior-aligned gates.

Same instrument batch / London clock as ``fx_v2b_london_ungated``:
  OR 03:00–03:15 America/New_York → flatten 11:59.

Gates (StrategyPlugin ``v2b_scaleout`` + fair ST+PMC 50/150 3R events):
  - prior_opposed: entry only after a same-session opposite-side ST event
  - prior_aligned: entry only after a same-session same-side ST event

Default ST tape: resting-limit hour-complete when orders exist, else fill stamps.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import session_bars
from .fx_v2b_london_ungated import (
    BOOKS,
    JPY_USD,
    LONDON,
    MARKETS,
    MarketSpec,
    REPO,
    _has_london_session,
    _progress,
    _regime_dates,
    _spread,
    _usd_norm,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .nq_v2b_prior_opposed_replay import load_st_events
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

GATES = ("prior_opposed", "prior_aligned")
DEFAULT_BOOK = "S_1_1_3"
ST_VARIANT = "sl50_tp150_3r_1mfill"


def _st_paths(symbol: str) -> Tuple[Path, Path, str]:
    sid = "%s_hourly_st_pmc_%s" % (symbol.lower(), ST_VARIANT)
    if symbol.upper() == "US30":
        root = REPO / "live" / "state" / "us30_st_pmc_runner_variants" / "states" / sid
    else:
        root = (
            REPO
            / "live"
            / "state"
            / "fx_index_metals_st_pmc_runner_variants"
            / symbol.lower()
            / "states"
            / sid
        )
    return root / "fills.csv", root / "orders.csv", sid


def _load_gate_events(symbol: str, output_root: Path) -> Tuple[Dict[str, List[Dict[str, str]]], str]:
    fills, orders, st_id = _st_paths(symbol)
    if not fills.exists() and not orders.exists():
        raise FileNotFoundError("Missing ST fills/orders for %s (%s)" % (symbol, fills))
    if orders.exists():
        mode = "resting_limit"
        _progress(output_root, "  %s ST gate=%s from orders (%s)" % (symbol, mode, st_id))
        events = load_st_events(
            fills if fills.exists() else orders,
            st_id,
            orders_path=orders,
            gate_mode=mode,
        )
    else:
        mode = "fill"
        _progress(output_root, "  %s ST gate=%s from fills (%s)" % (symbol, mode, st_id))
        events = load_st_events(fills, st_id, gate_mode=mode)
    n = sum(len(v) for v in events.values())
    _progress(output_root, "  %s ST events=%d sessions=%d" % (symbol, n, len(events)))
    return events, mode


def _strategy_id(symbol: str, gate: str, book: str) -> str:
    return "%s_v2b_london_%s_%s" % (symbol.lower(), gate, book)


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    gate: str,
    book: str,
    start: date,
    force: bool,
    max_days: Optional[int],
    gby: Optional[Dict[date, pd.DataFrame]] = None,
    regime_dates: Optional[List[date]] = None,
    session_frames: Optional[Dict[date, pd.DataFrame]] = None,
    st_events: Optional[Dict[str, List[Dict[str, str]]]] = None,
    gate_mode: str = "resting_limit",
) -> dict:
    if gate not in GATES:
        raise ValueError("gate must be one of %s" % (GATES,))
    sizing = BOOKS[book]
    entry_qty = sizing["entry_qty"]
    tp1_qty = sizing["tp1_qty"]
    tp2_qty = sizing["tp2_qty"]
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    strategy_id = _strategy_id(market.symbol, gate, book)
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
    daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())

    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick
    eff_start = start
    if market.start is not None and market.start > eff_start:
        eff_start = market.start

    if gby is None:
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    if regime_dates is None:
        regime_dates = _regime_dates(daily, gby, eff_start)
        regime_dates = [d for d in regime_dates if _has_london_session(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
    if st_events is None:
        st_events, gate_mode = _load_gate_events(market.symbol, output_root)

    _progress(output_root, "  %s %s %s sessions=%d" % (market.symbol, gate, book, len(regime_dates)))
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "market": market.symbol.lower(),
        "mode": "oco_then_reverse",
        "entry_qty": entry_qty,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "tick_size": market.tick,
        "rth_start": "03:00",
        "or_end": "03:15",
        "eod_cutoff": "11:59",
        "use_regime_filter": True,
        "prior_opposite_only": gate == "prior_opposed",
        "prior_aligned_only": gate == "prior_aligned",
        "prior_opposite_entry_qty": entry_qty if gate == "prior_opposed" else None,
        "prior_opposite_tp1_qty": tp1_qty if gate == "prior_opposed" else None,
        "prior_opposite_tp2_qty": tp2_qty if gate == "prior_opposed" else None,
        "dynamic_sizing_events": st_events,
        "gate_mode": gate_mode,
        "st_variant": ST_VARIANT,
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "regime_dates": [d.isoformat() for d in regime_dates],
        "record_levels": False,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2b_scaleout",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=entry_qty,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={market.symbol: market.tick},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(
            slippage_ticks=1.0,
            spread_model=_spread(market.tick, market.family),
        ),
    )
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        if session_frames is not None:
            df = session_frames.get(day)
            if df is None:
                continue
        else:
            df = session_bars(gby.get(day), day, LONDON, dense=True)
        if df is None or df.empty:
            continue
        for ts, row in df.iterrows():
            if pd.isna(row.get("close")):
                continue
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=market.symbol,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(one_m),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 250 == 0:
            _progress(output_root, "  %s %d/%d" % (strategy_id, idx, len(regime_dates)))
    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.symbol,
        fee_per_unit=market.fee_per_unit,
    )
    net = float(audit["net_usd"])
    stress = float(audit["intrabar_stress_dd_usd"])
    closed = float(audit["closed_dd_usd"])
    net_usd = _usd_norm(net, market.quote)
    stress_usd = _usd_norm(stress, market.quote)
    result = {
        "strategy_id": strategy_id,
        "symbol": market.symbol,
        "family": market.family,
        "quote": market.quote,
        "gate": gate,
        "book": book,
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "entry_qty": entry_qty,
        "regime_days": len(regime_dates),
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "gate_mode": gate_mode,
        "st_variant": ST_VARIANT,
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
        "net_native": net,
        "closed_dd_native": closed,
        "stress_dd_native": stress,
        "net_over_stress_native": (net / abs(stress)) if stress else 0.0,
        "net_usd": net_usd,
        "closed_dd_usd": _usd_norm(closed, market.quote),
        "stress_dd_usd": stress_usd,
        "net_over_stress": (net_usd / abs(stress_usd)) if stress_usd else 0.0,
        "win_rate": float(audit["win_rate"]),
        "profit_factor": float(audit["profit_factor"]),
        "max_open_units": int(audit["max_open_units"]),
        "state_root": str(state_root),
    }
    state_root.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_run_manifest(
        state_root,
        data_inputs=[one_m, daily, _st_paths(market.symbol)[0], _st_paths(market.symbol)[1]],
        output_paths=[metrics_path, state_root / "fills.csv"],
        strategy_config={k: v for k, v in payload.items() if k != "dynamic_sizing_events"},
        broker_realism_config={
            "slippage_ticks": 1.0,
            "fee_per_unit": market.fee_per_unit,
            "spread_model": "fx_eth_london" if market.family != "cfd" else "cfd_eth_london",
        },
        causality_mode="audit",
        extra={"driver": "fx_v2b_london_gated", "gate": gate, "book": book, "st_events": len(st_events)},
    )
    _progress(
        output_root,
        "DONE %s net_usd=%.2f N/S=%.2f trades=%d"
        % (strategy_id, result["net_usd"], result["net_over_stress"], result["trades"]),
    )
    return result


def write_summary(output_root: Path, rows: List[dict], gate: str) -> None:
    if not rows:
        return
    pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)
    ranked = sorted(rows, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    title = "prior-opposed" if gate == "prior_opposed" else "prior-aligned"
    lines = [
        "# FX / metals / CFD v2b London — %s S_1_1_3" % title,
        "",
        "StrategyPlugin: `v2b_scaleout` + ST+PMC `%s` gate (`%s`)." % (ST_VARIANT, gate),
        "",
        "London clock (America/New_York): OR **03:00–03:15**, flatten **11:59**.",
        "",
        "| Rank | Symbol | Gate | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.3f |"
            % (
                i,
                r["symbol"],
                r.get("gate", gate),
                int(r["regime_days"]),
                int(r["trades"]),
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["net_over_stress"]),
                float(r["win_rate"]),
                float(r["profit_factor"]),
            )
        )
    lines.extend(["", "- Hub: `%s`" % output_root.as_posix(), ""])
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = [
        "potions: fx_v2b_london_%s complete" % gate,
        "",
        "London OR 03:00–03:15 NY → flatten 11:59. Gate=%s book=S_1_1_3 ST=%s."
        % (gate, ST_VARIANT),
        "",
        "Top by N/S (USD-normalized):",
    ]
    for r in ranked[:12]:
        email.append(
            "  %s  N/S=%.2f  net≈$%.0f  stress≈$%.0f  trades=%d"
            % (
                r["symbol"],
                float(r["net_over_stress"]),
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                int(r["trades"]),
            )
        )
    email.extend(["", "Hub: %s" % output_root, "See INDEX.md / summary.csv."])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    markets: Sequence[str],
    gate: str,
    book: str,
    start: date,
    force: bool,
    max_days: Optional[int],
    email: bool,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    summary_path = output_root / "summary.csv"
    if summary_path.exists() and not force:
        try:
            rows = pd.read_csv(summary_path).to_dict("records")
        except Exception:
            rows = []
    seen = {str(r.get("symbol")) for r in rows}
    _progress(
        output_root,
        "START gate=%s book=%s london_open markets=%s" % (gate, book, ",".join(markets)),
    )
    errors: List[str] = []
    for name in markets:
        key = name.upper()
        if key not in MARKETS:
            raise ValueError("Unknown market %s" % name)
        market = MARKETS[key]
        sid = _strategy_id(key, gate, book)
        metrics_path = output_root / "states" / sid / "metrics.json"
        if (not force) and (key in seen or metrics_path.exists()):
            if metrics_path.exists() and key not in seen:
                row = json.loads(metrics_path.read_text(encoding="utf-8"))
                rows = [r for r in rows if str(r.get("symbol")) != key]
                rows.append(row)
                seen.add(key)
                write_summary(output_root, rows, gate)
            _progress(output_root, "SKIP cached %s" % sid)
            continue
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
        try:
            _progress(output_root, "LOAD %s 1m..." % key)
            gby = load_fx_1m_by_ny_date(one_m, market.symbol)
            eff_start = start
            if market.start is not None and market.start > eff_start:
                eff_start = market.start
            regime_dates = _regime_dates(daily, gby, eff_start)
            regime_dates = [d for d in regime_dates if _has_london_session(gby.get(d), d)]
            if max_days is not None:
                regime_dates = regime_dates[:max_days]
            st_events, gate_mode = _load_gate_events(key, output_root)
            _progress(output_root, "  %s densify london sessions=%d..." % (key, len(regime_dates)))
            session_frames: Dict[date, pd.DataFrame] = {}
            for i, day in enumerate(regime_dates, start=1):
                session_frames[day] = session_bars(gby.get(day), day, LONDON, dense=True)
                if i % 500 == 0:
                    _progress(output_root, "  %s densify %d/%d" % (key, i, len(regime_dates)))
            row = run_one(
                output_root=output_root,
                market=market,
                gate=gate,
                book=book,
                start=start,
                force=force,
                max_days=max_days,
                gby=gby,
                regime_dates=regime_dates,
                session_frames=session_frames,
                st_events=st_events,
                gate_mode=gate_mode,
            )
            rows = [r for r in rows if str(r.get("symbol")) != key]
            rows.append(row)
            seen.add(key)
            write_summary(output_root, rows, gate)
        except Exception as exc:
            tb = traceback.format_exc()
            errors.append("%s: %s" % (key, exc))
            _progress(output_root, "ERROR %s: %s" % (key, exc))
            (output_root / ("ERROR_%s.txt" % key)).write_text(tb, encoding="utf-8")
            write_summary(output_root, rows, gate)

    write_summary(output_root, rows, gate)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_v2b_london_%s complete" % gate, body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
            # Always try a minimal failure mail
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: fx_v2b_london_%s EMAIL/ partial" % gate,
                    body="Hub %s\nEmail body failed: %s\nErrors: %s\n" % (output_root, exc, errors),
                )
            except Exception:
                pass
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="London v2b prior-opposed / prior-aligned batch.")
    parser.add_argument("--gate", choices=GATES, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Default: live/state/fx_v2b_london_<gate>",
    )
    parser.add_argument("--start", default=date(2015, 1, 2).isoformat())
    parser.add_argument("--markets", default=",".join(MARKETS.keys()))
    parser.add_argument("--book", default=DEFAULT_BOOK, choices=sorted(BOOKS))
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args(argv)
    out = args.output_root or (REPO / "live" / "state" / ("fx_v2b_london_%s" % args.gate))
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    rows = run_batch(
        output_root=out,
        markets=markets,
        gate=args.gate,
        book=args.book,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
    )
    print("Wrote %s (%d rows)" % (out / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
