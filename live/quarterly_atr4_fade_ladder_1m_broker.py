"""Quarterly ±4×ATR fade ladder — 1m fill tape (4h signal bars).

Same StrategyPlugin book as ``quarterly_atr4_fade_ladder_broker``, but:
  - **4h** left-labeled bars drive signals only (``broker_fills=False``, shifted +4h)
  - **1m** tape resolves resting limits / stops (PaperBroker fills)
  - MTM audit on **4h** bars (bounded, no 1m lookahead on HTF signals)

Default hub: ``live/state/quarterly_atr4_fade_ladder_promising_1m_broker``
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_strategyplugin_variants import _broker_needs_1m
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .quarterly_atr4_fade_broker import MARKETS, MarketSpec, _spread
from .quarterly_atr4_fade_ladder_broker import BOOKS, load_4h, load_books_from_best_path
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_promising_1m_broker"
DEFAULT_BOOKS = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_promising" / "promising_books.csv"
BASELINE_SUMMARY = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_promising" / "summary.csv"
NY = "America/New_York"
SIGNAL_OFFSET_MIN = 240  # left-labeled 4h bar completes 4h after label
DSR = "TRL-2026-00158"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _1m_csv(market: MarketSpec) -> Path:
    return REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())


def _signal_bars(df: pd.DataFrame, market: MarketSpec) -> Tuple[List[Bar], List[AuditBar]]:
    out: List[Bar] = []
    audit: List[AuditBar] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        ts_s = pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        out.append(
            Bar(
                instrument=market.symbol,
                timeframe="4h",
                ts=ts_s,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(market.csv),
            )
        )
        audit.append(AuditBar(ts_s, o, h, l, c))
    return out, audit


def _replay_4h_with_1m(
    engine: Engine,
    *,
    signal_bars: Sequence[Bar],
    one_m: pd.DataFrame,
    market: MarketSpec,
    label: str,
    output_root: Path,
) -> int:
    offset = pd.Timedelta(minutes=SIGNAL_OFFSET_MIN)
    idx = one_m.index
    seen = 0
    skipped = 0
    n = len(signal_bars)
    cursor: Optional[pd.Timestamp] = None
    source = str(_1m_csv(market))

    def replay_1m_until(start: Optional[pd.Timestamp], end: pd.Timestamp) -> int:
        nonlocal seen
        if not _broker_needs_1m(engine):
            return 0
        lo = 0 if start is None else idx.searchsorted(start, side="left")
        hi = idx.searchsorted(end, side="left")
        if lo >= hi:
            return 0
        sl = one_m.iloc[lo:hi]
        vol = sl["volume"] if "volume" in sl.columns else None
        for j, (ts, o, h, l, c) in enumerate(
            zip(sl.index, sl["open"], sl["high"], sl["low"], sl["close"])
        ):
            if min(float(o), float(h), float(l), float(c)) <= 0:
                continue
            engine.process_bar(
                Bar(
                    instrument=market.symbol,
                    timeframe="1m",
                    ts=_utc_z(ts),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(vol.iloc[j]) if vol is not None else 0.0,
                    complete=True,
                    source=source,
                )
            )
            seen += 1
        return len(sl)

    for i, sbar in enumerate(signal_bars):
        signal_ts = pd.Timestamp(sbar.ts)
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.tz_localize("UTC")
        else:
            signal_ts = signal_ts.tz_convert("UTC")
        signal_ts = signal_ts + offset

        before = seen
        replay_1m_until(cursor, signal_ts)
        if seen == before and not _broker_needs_1m(engine):
            skipped += 1

        shifted = Bar(
            instrument=sbar.instrument,
            timeframe=sbar.timeframe,
            ts=_utc_z(signal_ts),
            open=sbar.open,
            high=sbar.high,
            low=sbar.low,
            close=sbar.close,
            volume=sbar.volume,
            complete=sbar.complete,
            source=sbar.source,
        )
        engine.process_bar(shifted, broker_fills=False)
        cursor = signal_ts

        if (i + 1) % 5000 == 0 or (i + 1) == n:
            _progress(
                output_root,
                "  %s signal %d/%d (1m=%d skipped=%d)"
                % (label, i + 1, n, seen, skipped),
            )

    if len(idx) > 0 and cursor is not None:
        replay_1m_until(cursor, idx[-1] + pd.Timedelta(minutes=1))
    _progress(output_root, "  %s done 1m=%d skipped_sig=%d" % (label, seen, skipped))
    return seen


def _baseline_4h(market: str) -> Tuple[float, float]:
    if not BASELINE_SUMMARY.exists():
        return 0.0, 0.0
    df = pd.read_csv(BASELINE_SUMMARY)
    hit = df[df["market"].astype(str).str.upper() == market.upper()]
    if hit.empty:
        return 0.0, 0.0
    row = hit.iloc[0]
    return float(row.get("net_over_stress") or 0.0), float(row.get("net_usd") or 0.0)


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    force: bool,
    book: Optional[Dict[str, object]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    strategy_id = "%s_quarterly_atr4_fade_ladder" % market.symbol.lower()
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    one_m_path = _1m_csv(market)
    if not one_m_path.exists():
        raise FileNotFoundError("Missing 1m tape for %s: %s" % (market.symbol, one_m_path))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = load_4h(market.csv, market.symbol)
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]

    _progress(output_root, "Loading %s 1m from %s ..." % (market.symbol, one_m_path))
    gby = load_fx_1m_by_ny_date(one_m_path, market.symbol)
    one_m = concat_all_1m(gby)
    if one_m.empty:
        raise RuntimeError("empty 1m tape for %s" % market.symbol)
    _progress(output_root, "  %s 4h=%d 1m=%d" % (market.symbol, len(df), len(one_m)))

    signal_bars, audit_bars = _signal_bars(df, market)

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = dict(book if book is not None else BOOKS[market.symbol])
    payload["tick_size"] = market.tick
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
        "  %s book=%s sides=%s risk=%.2f×ATR (feed=1m audit=4h)"
        % (
            market.symbol,
            payload["trade_mode"],
            ",".join(payload.get("allowed_sides") or []),
            float(payload["risk_atr_mult"]),
        ),
    )
    _replay_4h_with_1m(
        engine,
        signal_bars=signal_bars,
        one_m=one_m,
        market=market,
        label=strategy_id,
        output_root=output_root,
    )
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
    ns = (net / abs(stress)) if stress else 0.0
    base_ns, base_net = _baseline_4h(market.symbol)
    if ns >= base_ns * 0.85 and net > 0:
        stance = "retain — 1m fills hold vs 4h baseline"
    elif net > 0:
        stance = "weak — 1m degraded vs 4h"
    else:
        stance = "reject"

    metrics = {
        "strategy_id": strategy_id,
        "market": market.symbol,
        "feed_tf": "1m",
        "audit_tf": "4h",
        "trade_mode": payload["trade_mode"],
        "risk_atr_mult": float(payload["risk_atr_mult"]),
        "allowed_sides": list(payload.get("allowed_sides") or []),
        "path_id": str((book or BOOKS.get(market.symbol) or {}).get("path_id") or ""),
        "bars_4h": len(audit_bars),
        "bars_1m": len(one_m),
        "units": int(audit.get("units") or len(units)),
        "trades": int(audit.get("trades") or len({u.trade_id for u in units})),
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "win_rate": float(audit.get("win_rate") or 0.0) / 100.0,
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "net_over_stress": ns,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "baseline_4h_ns": base_ns,
        "baseline_4h_net_usd": base_net,
        "stance": stance,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f (4h was %.2f) trades=%d units=%d"
        % (market.symbol, metrics["net_usd"], ns, base_ns, metrics["trades"], metrics["units"]),
    )
    return metrics


def write_summary(output_root: Path, rows: Sequence[dict]) -> None:
    lines = [
        "# Quarterly ±4×ATR fade ladder — 1m fill tape",
        "",
        "Engine + PaperBroker: **4h** signal bars (`broker_fills=False`, +4h shift); "
        "**1m** resting fills; MTM audit on **4h**.",
        "10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).",
        "",
        "| Market | Path | Mode | Sides | Risk | 4h bars | Trades | Units | Net | Stress DD | N/S | 4h N/S | WR | PF | Stance |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for m in rows:
        stress = float(m.get("intrabar_stress_dd_usd") or 0.0)
        ns = float(m.get("net_over_stress") or 0.0)
        sides = m.get("allowed_sides") or []
        sides_s = ",".join(str(x) for x in sides) if isinstance(sides, (list, tuple)) else str(sides)
        lines.append(
            "| %s | %s | %s | %s | %.2f×ATR | %s | %d | %d | $%s | $%s | %.2f | %.2f | %.1f%% | %.2f | %s |"
            % (
                m["market"],
                m.get("path_id") or "",
                m.get("trade_mode") or "",
                sides_s,
                float(m.get("risk_atr_mult") or 0.0),
                f"{int(m.get('bars_4h') or 0):,}",
                int(m.get("trades") or 0),
                int(m.get("units") or 0),
                f"{float(m.get('net_usd') or 0.0):,.0f}",
                f"{stress:,.0f}",
                ns,
                float(m.get("baseline_4h_ns") or 0.0),
                100.0 * float(m.get("win_rate") or 0.0),
                float(m.get("profit_factor") or 0.0),
                m.get("stance") or "",
            )
        )
    lines += ["", "Hub: `%s`" % output_root, ""]
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(list(rows)).to_csv(output_root / "summary.csv", index=False)

    email = [
        "potions: quarterly ±4×ATR fade ladder 1m fills complete",
        "",
        "Hub: %s" % output_root.resolve(),
        "4h signals + 1m PaperBroker fills; audit on 4h.",
        "",
    ]
    for m in rows:
        email.append(
            "  %s  net=$%s  N/S=%.2f  (4h N/S=%.2f)  trades=%d  WR=%.0f%%  %s"
            % (
                m["market"],
                f"{float(m.get('net_usd') or 0.0):,.0f}",
                float(m.get("net_over_stress") or 0.0),
                float(m.get("baseline_4h_ns") or 0.0),
                int(m.get("trades") or 0),
                100.0 * float(m.get("win_rate") or 0.0),
                m.get("stance") or "",
            )
        )
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    symbols: Sequence[str],
    force: bool,
    email: bool,
    books: Optional[Dict[str, Dict[str, object]]] = None,
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
                raise SystemExit("No ladder book for %s" % sym)
            m = run_one(
                output_root=output_root,
                market=market,
                force=force,
                book=book_map[sym.upper()],
                start=start,
                end=end,
            )
            rows.append(m)
            log_run(
                run_class="broker_like",
                variant_slug="%s_quarterly_atr4_fade_ladder_1m" % sym.lower(),
                instrument=sym.upper(),
                hub_path=str(output_root.relative_to(REPO)),
                dsr_trial_id=DSR,
                net_usd=float(m.get("net_usd") or 0.0),
                stress_dd_usd=float(m.get("intrabar_stress_dd_usd") or 0.0),
                close_mtm_dd_usd=float(m.get("closed_dd_usd") or 0.0),
                ns=float(m.get("net_over_stress") or 0.0),
                trades=int(m.get("trades") or 0),
                meta={"feed_tf": "1m", "audit_tf": "4h", "baseline_4h_ns": m.get("baseline_4h_ns")},
            )
            write_summary(output_root, rows)
        write_summary(output_root, rows)
        write_run_manifest(
            output_root,
            data_inputs=[_1m_csv(MARKETS[s.upper()]) for s in symbols],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "plugin": "quarterly_atr4_fade_ladder",
                "feed_tf": "1m",
                "audit_tf": "4h",
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
            "potions: quarterly ladder 1m FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: quarterly ladder 1m FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        send_email(
            subject="potions: quarterly ±4×ATR fade ladder 1m fills complete",
            body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress(output_root, "email sent")
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symbol", action="append", default=None, help="Default GBPUSD + NAS100 (top 4h N/S)")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument(
        "--best-path",
        type=Path,
        nargs="?",
        const=DEFAULT_BOOKS,
        default=DEFAULT_BOOKS,
        help="Per-market books CSV (default promising_books.csv)",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbol or ["GBPUSD", "NAS100"]
    books = BOOKS
    if args.best_path is not None:
        bp = args.best_path
        if not bp.exists():
            raise SystemExit("best_path file missing: %s" % bp)
        books = load_books_from_best_path(bp)
    for s in symbols:
        if s.upper() not in MARKETS:
            raise SystemExit("Unknown symbol %s" % s)
        if s.upper() not in books:
            raise SystemExit("No ladder book for %s" % s)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    run_batch(
        output_root=args.output_root,
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
