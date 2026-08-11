"""Asia session range → v2b OCO from London open — FX majors.

Opening range = **Asian session** high/low (America/New_York):
  - Asia watch: previous **19:00** → London open **03:00** (exclusive)
  - Arm classic v2b OCO stops at Asia H/L when London starts (**03:00**)
  - Flatten **11:59** (same London book eod)

Uses StrategyPlugin ``v2b_scaleout`` with ``session_or_ranges`` (precomputed Asia
H/L) so the overnight OR does not rely on same-calendar-day ``[rth_start, or_end)``.

Default markets: EURUSD, GBPUSD, USDJPY. Books: any ``S_tp1_tp2_runner``
(e.g. S_1_1_3, S_3_1_1, S_0_2_3). Hub → ``live/state/fx_v2b_asia_range_london/``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import CLOCKS, session_bars
from .fx_v2b_london_ungated import (
    MARKETS,
    MarketSpec,
    REPO,
    _has_london_session,
    _progress,
    _regime_dates,
    _spread,
    _usd_norm,
    resolve_book,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

DEFAULT_OUT = REPO / "live" / "state" / "fx_v2b_asia_range_london"
LONDON = CLOCKS["london_open"]
DEFAULT_MAJORS = ("EURUSD", "GBPUSD", "USDJPY")
ASIA_START = time(19, 0)  # NY prior evening (Tokyo open-ish)
ASIA_END = time(3, 0)  # London open — exclusive
MIN_ASIA_BARS = 180  # ~3h coverage floor inside the 8h Asia window


def _asia_hilo(gby: Dict[date, pd.DataFrame], session: date) -> Optional[Tuple[float, float, int]]:
    """Asia range for the London session date: [prev 19:00, session 03:00)."""
    frames: List[pd.DataFrame] = []
    prev = session - timedelta(days=1)
    prev_df = gby.get(prev)
    cur_df = gby.get(session)
    if prev_df is not None and not prev_df.empty:
        part = prev_df[prev_df.index.map(lambda ts: ts.time() >= ASIA_START)]
        if not part.empty:
            frames.append(part)
    if cur_df is not None and not cur_df.empty:
        part = cur_df[cur_df.index.map(lambda ts: ts.time() < ASIA_END)]
        if not part.empty:
            frames.append(part)
    if not frames:
        return None
    asia = pd.concat(frames).sort_index()
    asia = asia[~asia.index.duplicated(keep="last")]
    if len(asia) < MIN_ASIA_BARS:
        return None
    hi = float(asia["high"].max())
    lo = float(asia["low"].min())
    if hi <= lo:
        return None
    return hi, lo, len(asia)


def build_session_asia_ranges(
    gby: Dict[date, pd.DataFrame], sessions: Sequence[date]
) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for session in sessions:
        hilo = _asia_hilo(gby, session)
        if hilo is None:
            continue
        hi, lo, n = hilo
        out[session.isoformat()] = {
            "high": hi,
            "low": lo,
            "range": hi - lo,
            "asia_bars": n,
            "asia_window": "19:00-03:00",
        }
    return out


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    book: str,
    start: date,
    force: bool,
    max_days: Optional[int],
    gby: Optional[Dict[date, pd.DataFrame]] = None,
    regime_dates: Optional[List[date]] = None,
    session_frames: Optional[Dict[date, pd.DataFrame]] = None,
    session_asia_ranges: Optional[Dict[str, dict]] = None,
) -> dict:
    sizing = resolve_book(book)
    entry_qty = sizing["entry_qty"]
    tp1_qty = sizing["tp1_qty"]
    tp2_qty = sizing["tp2_qty"]
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    strategy_id = "%s_v2b_asia_range_london_%s" % (market.symbol.lower(), book)
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
        regime_dates = [d for d in _regime_dates(daily, gby, eff_start) if _has_london_session(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
    if session_asia_ranges is None:
        session_asia_ranges = build_session_asia_ranges(gby, regime_dates)
    # Only trade days with a usable Asia range.
    regime_dates = [d for d in regime_dates if d.isoformat() in session_asia_ranges]

    _progress(output_root, "  %s %s sessions=%d" % (market.symbol, book, len(regime_dates)))
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
        "or_end": "03:00",
        "or_bars": 1,
        "eod_cutoff": "11:59",
        "use_regime_filter": True,
        "prior_opposite_only": False,
        "start": eff_start.isoformat(),
        "clock": "asia_range_london",
        "asia_window": "19:00-03:00",
        "regime_dates": [d.isoformat() for d in regime_dates],
        "session_or_ranges": session_asia_ranges,
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
        "book": book,
        "clock": "asia_range_london",
        "or_window": "19:00-03:00",
        "or_bars": "asia_precomputed",
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "regime_days": len(regime_dates),
        "start": eff_start.isoformat(),
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
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
        data_inputs=[one_m, daily],
        output_paths=[metrics_path, state_root / "fills.csv"],
        strategy_config=payload,
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": market.fee_per_unit},
        causality_mode="audit",
        extra={"driver": "fx_v2b_asia_range_london", "book": book},
    )
    _progress(
        output_root,
        "DONE %s net_usd=%.2f N/S=%.2f trades=%d"
        % (strategy_id, result["net_usd"], result["net_over_stress"], result["trades"]),
    )
    return result


def write_summary(output_root: Path, rows: List[dict]) -> None:
    if not rows:
        return
    pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)
    ranked = sorted(rows, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    lines = [
        "# FX majors v2b — **Asia session range** breakout (arm at London 03:00)",
        "",
        "Asia OR **19:00–03:00** NY (precomputed) → arm OCO at London open → flatten **11:59**.",
        "StrategyPlugin `v2b_scaleout` + `session_or_ranges`.",
        "",
        "| Rank | Symbol | Book | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.3f |"
            % (
                i,
                r["symbol"],
                r["book"],
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
        "potions: fx_v2b_asia_range_london complete",
        "",
        "Asia range 19:00–03:00 NY → v2b OCO at London 03:00 → flatten 11:59.",
        "Broker-like Engine+PaperBroker. FX majors.",
        "",
        "Top by N/S:",
    ]
    for r in ranked[:12]:
        email.append(
            "  %s %s  N/S=%.2f  net≈$%.0f  trades=%d"
            % (r["symbol"], r["book"], float(r["net_over_stress"]), float(r["net_usd"]), int(r["trades"]))
        )
    email.extend(["", "Hub: %s" % output_root])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    markets: Sequence[str],
    books: Sequence[str],
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
    seen = {(str(r.get("symbol")), str(r.get("book"))) for r in rows}
    _progress(output_root, "START asia_range_london markets=%s books=%s" % (",".join(markets), ",".join(books)))
    errors: List[str] = []
    for name in markets:
        key = name.upper()
        market = MARKETS[key]
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
        pending = [
            b
            for b in books
            if force
            or (
                (key, b) not in seen
                and not (
                    output_root / "states" / ("%s_v2b_asia_range_london_%s" % (key.lower(), b)) / "metrics.json"
                ).exists()
            )
        ]
        if not pending:
            for book in books:
                mp = output_root / "states" / ("%s_v2b_asia_range_london_%s" % (key.lower(), book)) / "metrics.json"
                if mp.exists() and (key, book) not in seen:
                    rows.append(json.loads(mp.read_text(encoding="utf-8")))
                    seen.add((key, book))
            write_summary(output_root, rows)
            continue
        try:
            _progress(output_root, "LOAD %s..." % key)
            gby = load_fx_1m_by_ny_date(one_m, market.symbol)
            eff_start = start if market.start is None else max(start, market.start)
            regime_dates = [d for d in _regime_dates(daily, gby, eff_start) if _has_london_session(gby.get(d), d)]
            if max_days is not None:
                regime_dates = regime_dates[:max_days]
            session_asia_ranges = build_session_asia_ranges(gby, regime_dates)
            regime_dates = [d for d in regime_dates if d.isoformat() in session_asia_ranges]
            session_frames: Dict[date, pd.DataFrame] = {
                day: session_bars(gby.get(day), day, LONDON, dense=True) for day in regime_dates
            }
            _progress(
                output_root,
                "  %s sessions=%d asia_ranges=%d" % (key, len(regime_dates), len(session_asia_ranges)),
            )
        except Exception as exc:
            errors.append("%s LOAD: %s" % (key, exc))
            (output_root / ("ERROR_%s_LOAD.txt" % key)).write_text(traceback.format_exc(), encoding="utf-8")
            continue
        for book in books:
            if (not force) and (key, book) in seen:
                continue
            try:
                row = run_one(
                    output_root=output_root,
                    market=market,
                    book=book,
                    start=start,
                    force=force,
                    max_days=max_days,
                    gby=gby,
                    regime_dates=regime_dates,
                    session_frames=session_frames,
                    session_asia_ranges=session_asia_ranges,
                )
                rows = [r for r in rows if not (str(r.get("symbol")) == key and str(r.get("book")) == book)]
                rows.append(row)
                seen.add((key, book))
                write_summary(output_root, rows)
            except Exception as exc:
                errors.append("%s %s: %s" % (key, book, exc))
                _progress(output_root, "ERROR %s %s: %s" % (key, book, exc))
                (output_root / ("ERROR_%s_%s.txt" % (key, book))).write_text(traceback.format_exc(), encoding="utf-8")
    write_summary(output_root, rows)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_v2b_asia_range_london complete", body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: fx_v2b_asia_range_london EMAIL/ partial",
                    body="Hub: %s\nEmail issue: %s\nErrors: %s" % (output_root, exc, errors),
                )
            except Exception:
                pass
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--start", default="2015-01-02")
    p.add_argument("--markets", default=",".join(DEFAULT_MAJORS))
    p.add_argument(
        "--books",
        default="S_1_1_3,S_1_1_1",
        help="Comma list of S_tp1_tp2_runner books (e.g. S_1_1_3,S_3_1_1,S_0_2_3).",
    )
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--no-force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    rows = run_batch(
        output_root=args.output_root,
        markets=[m.strip().upper() for m in args.markets.split(",") if m.strip()],
        books=[b.strip() for b in args.books.split(",") if b.strip()],
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
    )
    print("Wrote %s (%d rows)" % (args.output_root / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
