"""Broker-like Engine+PaperBroker replay: quarterly ±4×ATR fade ATR ladder.

Books (StrategyPlugin ``quarterly_atr4_fade_ladder``):

Default family heuristics (overridden by ``--best-path``):

FX / metals
  - Fade from lower only (first touch); skip upper-first quarters
  - 10 contracts; risk 2×ATR
  - Scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then SL→BE; 2 runners to EOQ

Index CFDs / futures
  - Second-path only (first touch → opposite ±4 before same-side ±8)
  - 10 contracts; risk 0.5×ATR
  - Same ATR scale ladder + BE runners to EOQ

``--best-path`` loads ``best_path.csv`` from the opposite-path study and sets
per-market ``trade_mode`` / ``allowed_sides`` / ``risk_atr_mult``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .quarterly_atr4_fade_broker import ALL_SYMBOLS, MARKETS, MarketSpec, load_4h, _spread
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_fade_ladder"
DEFAULT_BEST_PATH = REPO / "live" / "state" / "quarterly_atr4_opposite_path" / "best_path.csv"
DEFAULT_BEST_OUT = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_best_path"


def _base_book() -> Dict[str, Any]:
    return {
        "entry_qty": 10,
        "scale_qty": 2,
        "scale_atr_step": 2.0,
        "be_after_atr": 8.0,
        "atr_len": 14,
        "atr_mult": 4.0,
        "risk_atr_mult": 2.0,
        "trade_mode": "first_only",
        "allowed_sides": ["lower"],
        "max_trades_per_quarter": 1,
        "timeframe": "4h",
        "record_levels": False,
        "suppress_alerts": True,
    }


def _fx_metal_book() -> Dict[str, Any]:
    """GBPUSD-style: fade lower-first only; risk 2×ATR; 10ct ladder."""
    b = _base_book()
    b.update(
        {
            "risk_atr_mult": 2.0,
            "trade_mode": "first_only",
            "allowed_sides": ["lower"],
        }
    )
    return b


def _index_book() -> Dict[str, Any]:
    """US30-style: second-path only; risk 0.5×ATR; 10ct ladder."""
    b = _base_book()
    b.update(
        {
            "risk_atr_mult": 0.5,
            "trade_mode": "second_only",
            "allowed_sides": ["lower", "upper"],
        }
    )
    return b


def default_books() -> Dict[str, Dict[str, Any]]:
    return {
        sym: (_fx_metal_book() if m.family in {"fx", "metal"} else _index_book())
        for sym, m in MARKETS.items()
    }


BOOKS: Dict[str, Dict[str, Any]] = default_books()


def load_books_from_best_path(path: Path) -> Dict[str, Dict[str, Any]]:
    """Build per-market ladder books from opposite-path ``best_path.csv``."""
    df = pd.read_csv(path)
    books = default_books()
    for _, row in df.iterrows():
        sym = str(row["market"]).upper()
        if sym not in MARKETS:
            continue
        b = _base_book()
        mode = str(row.get("trade_mode") or "first_only").strip().lower()
        sides_raw = row.get("allowed_sides")
        if isinstance(sides_raw, float) and pd.isna(sides_raw):
            sides = ["lower", "upper"]
        else:
            sides = [s.strip().lower() for s in str(sides_raw).split(",") if s.strip()]
        if not sides:
            sides = ["lower", "upper"]
        risk = float(row.get("risk_atr_mult") or 2.0)
        b.update(
            {
                "trade_mode": mode,
                "allowed_sides": sides,
                "risk_atr_mult": risk,
                "path_id": str(row.get("path_id") or ""),
                "path_win_rate": float(row.get("win_rate") or 0.0),
            }
        )
        books[sym] = b
    return books


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    force: bool,
    book: Optional[Dict[str, Any]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    strategy_id = "%s_quarterly_atr4_fade_ladder" % market.symbol.lower()
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = load_4h(market.csv, market.symbol)
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz="America/New_York")]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz="America/New_York") + pd.Timedelta(days=1)]

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = dict(book if book is not None else BOOKS[market.symbol])
    payload["tick_size"] = market.tick
    # path_id / path_win_rate are study metadata — keep out of plugin config.
    payload.pop("path_id", None)
    payload.pop("path_win_rate", None)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="quarterly_atr4_fade_ladder",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4h",
                    max_contracts=int(payload.get("entry_qty") or 10),
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
    _progress(
        output_root,
        "  %s bars=%s book=%s sides=%s risk=%.2f×ATR"
        % (
            market.symbol,
            f"{len(df):,}",
            payload["trade_mode"],
            ",".join(payload.get("allowed_sides") or []),
            float(payload["risk_atr_mult"]),
        ),
    )
    audit_bars: List[AuditBar] = []
    n = 0
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        ts_s = pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")
        bar = Bar(
            instrument=market.symbol,
            timeframe="4h",
            ts=ts_s,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            complete=True,
            source=str(market.csv),
        )
        engine.process_bar(bar)
        audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        n += 1
        if n % 5000 == 0:
            _progress(output_root, "  %s %d/%d" % (strategy_id, n, len(df)))
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
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    metrics = {
        "strategy_id": strategy_id,
        "market": market.symbol,
        "trade_mode": payload["trade_mode"],
        "risk_atr_mult": float(payload["risk_atr_mult"]),
        "allowed_sides": list(payload.get("allowed_sides") or []),
        "path_id": str((book or BOOKS.get(market.symbol) or {}).get("path_id") or ""),
        "bars": len(audit_bars),
        "units": int(audit.get("units") or len(units)),
        "trades": int(audit.get("trades") or len({u.trade_id for u in units})),
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "win_rate": float(audit.get("win_rate") or 0.0) / 100.0,
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "max_open_units": int(audit.get("max_open_units") or 0),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d units=%d"
        % (
            market.symbol,
            metrics["net_usd"],
            metrics["net_over_stress"],
            metrics["trades"],
            metrics["units"],
        ),
    )
    return metrics


def write_summary(output_root: Path, rows: Sequence[dict]) -> None:
    lines = [
        "# Quarterly ±4×ATR fade ladder (broker-like)",
        "",
        "Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14).",
        "10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).",
        "Mode / sides / risk come from per-market book (family default or best-path).",
        "",
        "| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    csv_rows = []
    for m in rows:
        stress = float(m.get("intrabar_stress_dd_usd") or 0.0)
        ns = float(m.get("net_over_stress") or 0.0)
        sides = m.get("allowed_sides") or []
        if isinstance(sides, (list, tuple)):
            sides_s = ",".join(str(x) for x in sides)
        else:
            sides_s = str(sides)
        lines.append(
            "| %s | %s | %s | %s | %.2f×ATR | %s | %d | %d | $%s | $%s | %.2f | %.1f%% | %.2f |"
            % (
                m["market"],
                m.get("path_id") or "",
                m.get("trade_mode") or "",
                sides_s,
                float(m.get("risk_atr_mult") or 0.0),
                f"{int(m.get('bars') or 0):,}",
                int(m.get("trades") or 0),
                int(m.get("units") or 0),
                f"{float(m.get('net_usd') or 0.0):,.0f}",
                f"{stress:,.0f}",
                ns,
                100.0 * float(m.get("win_rate") or 0.0),
                float(m.get("profit_factor") or 0.0),
            )
        )
        csv_rows.append(m)
    lines += [
        "",
        "Hub: `%s`" % output_root,
        "",
        "Promote gate: research until causality audit + multi-year N/S hold.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(csv_rows).to_csv(output_root / "summary.csv", index=False)

    email = [
        "potions: quarterly ±4×ATR fade ladder broker-like complete",
        "",
        "Hub: %s" % output_root.resolve(),
        "Per-market path/mode/risk; 10ct ladder: 2 off @ +2/+4/+6/+8 ATR, BE + 2 runners to EOQ.",
        "",
    ]
    for m in rows:
        email.append(
            "  %s  %s  %s  risk=%.2f×ATR  net=$%s  N/S=%.2f  trades=%d  WR=%.0f%%  PF=%.2f"
            % (
                m["market"],
                m.get("path_id") or "-",
                m.get("trade_mode") or "",
                float(m.get("risk_atr_mult") or 0.0),
                f"{float(m.get('net_usd') or 0.0):,.0f}",
                float(m.get("net_over_stress") or 0.0),
                int(m.get("trades") or 0),
                100.0 * float(m.get("win_rate") or 0.0),
                float(m.get("profit_factor") or 0.0),
            )
        )
    email += ["", "See SUMMARY.md for table."]
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    symbols: Sequence[str],
    force: bool,
    email: bool,
    books: Optional[Dict[str, Dict[str, Any]]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    book_map = books if books is not None else BOOKS
    rows: List[dict] = []
    try:
        for sym in symbols:
            market = MARKETS[sym.upper()]
            if sym.upper() not in book_map:
                raise SystemExit("No ladder book for %s (have %s)" % (sym, ",".join(book_map)))
            rows.append(
                run_one(
                    output_root=output_root,
                    market=market,
                    force=force,
                    book=book_map[sym.upper()],
                    start=start,
                    end=end,
                )
            )
            write_summary(output_root, rows)
        write_summary(output_root, rows)
        write_run_manifest(
            output_root,
            data_inputs=[MARKETS[s.upper()].csv for s in symbols],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "plugin": "quarterly_atr4_fade_ladder",
                "books": {s: book_map[s.upper()] for s in symbols},
            },
            broker_realism_config={"slippage_ticks": 1.0},
            extra={"markets": list(symbols)},
        )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "markets": list(symbols)}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: quarterly ±4×ATR fade ladder FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: quarterly ±4×ATR fade ladder FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(subject="potions: quarterly ±4×ATR fade ladder broker-like complete", body=body)
        _progress(output_root, "email sent")
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="Repeatable; default all FX/metals/CFDs/futures in MARKETS",
    )
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument(
        "--best-path",
        type=Path,
        nargs="?",
        const=DEFAULT_BEST_PATH,
        default=None,
        help="Load books from opposite-path best_path.csv (default path if flag alone)",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbol or list(ALL_SYMBOLS)
    books = BOOKS
    output_root = args.output_root
    if args.best_path is not None:
        bp = args.best_path
        if not bp.exists():
            raise SystemExit("best_path file missing: %s" % bp)
        books = load_books_from_best_path(bp)
        if output_root is None:
            output_root = DEFAULT_BEST_OUT
    if output_root is None:
        output_root = DEFAULT_OUT
    for s in symbols:
        if s.upper() not in MARKETS:
            raise SystemExit("Unknown symbol %s (want %s)" % (s, ",".join(MARKETS)))
        if s.upper() not in books:
            raise SystemExit("No ladder book for %s" % s)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    run_batch(
        output_root=output_root,
        symbols=symbols,
        force=args.force,
        email=args.email,
        books=books,
        start=start,
        end=end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
