"""Ungated v2b OCO on FX / metals / index CFDs using the London session clock.

London clock (America/New_York), from ``fx_or_markets.CLOCKS['london_open']``:
  - Opening range: **03:00–03:15**
  - Session / densify → **11:59** (flatten at ``eod_cutoff``)

Not 02:00 / 02:30 — those are common London cash-open guesses in EST; this
repo's OR book is explicitly 03:00 NY.

Books (StrategyPlugin ``v2b_scaleout``, no prior-opposed gate):
  - S_1_1_1 → entry 3 / tp1 1 / tp2 1 / runner 1
  - S_1_1_3 → entry 5 / tp1 1 / tp2 1 / runner 3
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import CLOCKS, session_bars
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "fx_v2b_london_ungated"
DEFAULT_START = date(2015, 1, 2)
LONDON = CLOCKS["london_open"]
JPY_USD = 110.0

BOOKS: Dict[str, Dict[str, int]] = {
    "S_1_1_1": {"entry_qty": 3, "tp1_qty": 1, "tp2_qty": 1},
    "S_1_1_3": {"entry_qty": 5, "tp1_qty": 1, "tp2_qty": 1},
}


def resolve_book(book: str) -> Dict[str, int]:
    """Resolve ``S_tp1_tp2_runner`` (or a named BOOKS entry) to entry/tp1/tp2 qty.

    Runner is implicit: ``entry_qty - tp1_qty - tp2_qty``. Zero buckets are
    allowed (plugin skips TP1/TP2 orders when qty is 0).
    """
    if book in BOOKS:
        return dict(BOOKS[book])
    parts = book.split("_")
    if len(parts) == 4 and parts[0] == "S":
        try:
            tp1, tp2, runner = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError as exc:
            raise KeyError("Invalid book %r (need S_tp1_tp2_runner)" % book) from exc
        if min(tp1, tp2, runner) < 0:
            raise KeyError("Negative qty in book %r" % book)
        entry = tp1 + tp2 + runner
        if entry <= 0:
            raise KeyError("Zero entry in book %r" % book)
        return {"entry_qty": entry, "tp1_qty": tp1, "tp2_qty": tp2}
    raise KeyError("Unknown book %r (expected S_tp1_tp2_runner)" % book)


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    tick: float
    point_value: float
    fee_per_unit: float
    quote: str  # USD | JPY
    family: str  # fx | metal | cfd
    start: Optional[date] = None


MARKETS: Dict[str, MarketSpec] = {
    "EURUSD": MarketSpec("EURUSD", 0.00001, 100_000.0, 7.0, "USD", "fx"),
    "GBPUSD": MarketSpec("GBPUSD", 0.00001, 100_000.0, 7.0, "USD", "fx"),
    "USDJPY": MarketSpec("USDJPY", 0.001, 100_000.0, 7.0, "JPY", "fx"),
    "AUDJPY": MarketSpec("AUDJPY", 0.001, 100_000.0, 7.0, "JPY", "fx"),
    "XAUUSD": MarketSpec("XAUUSD", 0.01, 100.0, 7.0, "USD", "metal"),
    "XAGUSD": MarketSpec("XAGUSD", 0.001, 1000.0, 7.0, "USD", "metal"),
    "US30": MarketSpec("US30", 0.1, 1.0, 1.50, "USD", "cfd", date(2021, 1, 4)),
    "NAS100": MarketSpec("NAS100", 0.1, 1.0, 1.50, "USD", "cfd", date(2021, 1, 4)),
}


def _progress(output_root: Path, message: str) -> None:
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _spread(tick: float, family: str) -> SpreadModel:
    if family == "cfd":
        return SpreadModel(
            rth_half_spread_ticks=0.5,
            eth_half_spread_ticks=1.0,
            open_widen_half_spread_ticks=1.0,
            low_volume_threshold=1.0,
            low_volume_multiplier=1.5,
            tick_size=tick,
        )
    # FX / metals: ~0.5 pip RTH, ~1.0 pip ETH (London hours hit ETH path).
    return SpreadModel(
        rth_half_spread_ticks=5.0,
        eth_half_spread_ticks=10.0,
        open_widen_half_spread_ticks=10.0,
        low_volume_threshold=1.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def _regime_dates(daily_path: Path, gby: Dict[date, pd.DataFrame], start: date) -> List[date]:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    daily["ma50"] = pd.to_numeric(daily["close"], errors="coerce").rolling(50).mean()
    daily["ma150"] = pd.to_numeric(daily["close"], errors="coerce").rolling(150).mean()
    daily["eligible"] = (daily["ma50"] > daily["ma150"]).shift(1).fillna(False)
    eligible = {pd.Timestamp(row["date"]).date() for _, row in daily[daily["eligible"]].iterrows()}
    return [day for day in sorted(gby) if day in eligible and day >= start]


def _has_london_session(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    raw = session_bars(raw_day, session, LONDON, dense=False)
    if raw.empty or len(raw) < max(40, LONDON.min_session_bars // 3):
        return False
    or_slice = raw[raw.index.map(lambda ts: ts.time() < LONDON.or_end)]
    return len(or_slice) >= LONDON.min_or_bars


def _usd_norm(value: float, quote: str) -> float:
    return value / JPY_USD if quote == "JPY" else value


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
) -> dict:
    sizing = resolve_book(book)
    entry_qty = sizing["entry_qty"]
    tp1_qty = sizing["tp1_qty"]
    tp2_qty = sizing["tp2_qty"]
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    strategy_id = "%s_v2b_london_%s" % (market.symbol.lower(), book)
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
    daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
    if not one_m.exists():
        raise FileNotFoundError(one_m)
    if not daily.exists():
        raise FileNotFoundError(daily)

    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick
    eff_start = start
    if market.start is not None and market.start > eff_start:
        eff_start = market.start

    if gby is None:
        _progress(output_root, "LOAD %s 1m for %s..." % (market.symbol, book))
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    if regime_dates is None:
        regime_dates = _regime_dates(daily, gby, eff_start)
        regime_dates = [d for d in regime_dates if _has_london_session(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
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
        "or_end": "03:15",
        "eod_cutoff": "11:59",
        "use_regime_filter": True,
        "prior_opposite_only": False,
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
        "book": book,
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "entry_qty": entry_qty,
        "regime_days": len(regime_dates),
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "rth_start": "03:00",
        "or_end": "03:15",
        "eod_cutoff": "11:59",
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
        data_inputs=[one_m, daily],
        output_paths=[metrics_path, state_root / "fills.csv"],
        strategy_config=payload,
        broker_realism_config={
            "slippage_ticks": 1.0,
            "fee_per_unit": market.fee_per_unit,
            "spread_model": "fx_eth_london" if market.family != "cfd" else "cfd_eth_london",
        },
        causality_mode="audit",
        extra={"driver": "fx_v2b_london_ungated", "book": book},
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
        "# FX / metals / CFD ungated v2b — London session",
        "",
        "StrategyPlugin: `v2b_scaleout` (OCO, no prior-opposed gate).",
        "",
        "London clock (America/New_York):",
        "- OR **03:00–03:15** (not ~02:00 / 02:30)",
        "- Flatten **11:59**",
        "",
        "JPY pairs reported with native P&L and ≈USD via `/110`.",
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
    lines.extend(
        [
            "",
            "- Hub: `%s`" % output_root.as_posix(),
            "- Fee: FX/metals $7/unit; US30/NAS100 $1.50/unit; 1-tick slip + ETH-aware spread.",
            "",
        ]
    )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = [
        "potions: fx_v2b_london_ungated complete",
        "",
        "London OR 03:00–03:15 NY → flatten 11:59. Books: %s"
        % ", ".join(sorted({r["book"] for r in rows})),
        "",
        "Top by N/S (USD-normalized):",
    ]
    for r in ranked[:12]:
        email.append(
            "  %s %s  N/S=%.2f  net≈$%.0f  stress≈$%.0f  trades=%d"
            % (
                r["symbol"],
                r["book"],
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
    books: Sequence[str],
    start: date,
    force: bool,
    max_days: Optional[int],
    email: bool,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    # Resume-friendly: keep prior metrics when not forcing full wipe.
    summary_path = output_root / "summary.csv"
    if summary_path.exists() and not force:
        try:
            rows = pd.read_csv(summary_path).to_dict("records")
        except Exception:
            rows = []
    seen = {(str(r.get("symbol")), str(r.get("book"))) for r in rows}

    _progress(
        output_root,
        "START london_open OR=03:00-03:15 eod=11:59 markets=%s books=%s"
        % (",".join(markets), ",".join(books)),
    )
    errors: List[str] = []
    for book in books:
        if book not in BOOKS:
            raise ValueError("Unknown book %s (want %s)" % (book, sorted(BOOKS)))
    for name in markets:
        key = name.upper()
        if key not in MARKETS:
            raise ValueError("Unknown market %s" % name)
        market = MARKETS[key]
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
        pending = [b for b in books if force or (key, b) not in seen]
        # Still honor per-book metrics.json cache inside run_one.
        pending = [
            b
            for b in pending
            if force or not (output_root / "states" / ("%s_v2b_london_%s" % (key.lower(), b)) / "metrics.json").exists()
        ]
        if not pending:
            _progress(output_root, "SKIP all books cached for %s" % key)
            for book in books:
                metrics_path = output_root / "states" / ("%s_v2b_london_%s" % (key.lower(), book)) / "metrics.json"
                if metrics_path.exists() and (key, book) not in seen:
                    row = json.loads(metrics_path.read_text(encoding="utf-8"))
                    rows = [r for r in rows if not (str(r.get("symbol")) == key and str(r.get("book")) == book)]
                    rows.append(row)
                    seen.add((key, book))
            write_summary(output_root, rows)
            continue
        try:
            _progress(output_root, "LOAD %s 1m (shared for books=%s)..." % (key, ",".join(pending)))
            gby = load_fx_1m_by_ny_date(one_m, market.symbol)
            eff_start = start
            if market.start is not None and market.start > eff_start:
                eff_start = market.start
            regime_dates = _regime_dates(daily, gby, eff_start)
            regime_dates = [d for d in regime_dates if _has_london_session(gby.get(d), d)]
            if max_days is not None:
                regime_dates = regime_dates[:max_days]
            _progress(output_root, "  %s london regime sessions=%d" % (key, len(regime_dates)))
            _progress(output_root, "  %s densify london sessions..." % key)
            session_frames: Dict[date, pd.DataFrame] = {}
            for i, day in enumerate(regime_dates, start=1):
                session_frames[day] = session_bars(gby.get(day), day, LONDON, dense=True)
                if i % 500 == 0:
                    _progress(output_root, "  %s densify %d/%d" % (key, i, len(regime_dates)))
        except Exception as exc:
            tb = traceback.format_exc()
            errors.append("%s LOAD: %s" % (key, exc))
            _progress(output_root, "ERROR %s LOAD: %s" % (key, exc))
            (output_root / ("ERROR_%s_LOAD.txt" % key)).write_text(tb, encoding="utf-8")
            continue
        for book in books:
            if (not force) and (key, book) in seen:
                _progress(output_root, "SKIP already in summary %s %s" % (key, book))
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
                )
                rows = [r for r in rows if not (str(r.get("symbol")) == key and str(r.get("book")) == book)]
                rows.append(row)
                seen.add((key, book))
                write_summary(output_root, rows)
            except Exception as exc:
                tb = traceback.format_exc()
                errors.append("%s %s: %s" % (key, book, exc))
                _progress(output_root, "ERROR %s %s: %s" % (key, book, exc))
                (output_root / ("ERROR_%s_%s.txt" % (key, book))).write_text(tb, encoding="utf-8")
                write_summary(output_root, rows)

    write_summary(output_root, rows)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_v2b_london_ungated complete", body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="London-session ungated v2b across FX/metals/CFDs.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument(
        "--markets",
        default=",".join(MARKETS.keys()),
        help="Comma list (default: all FX/metals/CFDs).",
    )
    parser.add_argument("--books", default="S_1_1_3,S_1_1_1", help="Comma list of S_1_1_1 / S_1_1_3.")
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--no-force", action="store_true", help="Reuse cached metrics.json when present.")
    parser.add_argument("--email", action="store_true", help="Email EMAIL.txt via Resend on finish.")
    args = parser.parse_args(argv)
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    books = [b.strip() for b in args.books.split(",") if b.strip()]
    rows = run_batch(
        output_root=args.output_root,
        markets=markets,
        books=books,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
    )
    print("Wrote %s (%d rows)" % (args.output_root / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
