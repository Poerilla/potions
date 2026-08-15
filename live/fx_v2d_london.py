"""Canonical v2d fade on FX / metals / index CFDs using the London session clock.

London clock (America/New_York), from ``fx_or_markets.CLOCKS['london_open']``:
  - Opening range: **03:00–03:15**
  - Session / densify → **11:59** (flatten at ``eod_cutoff``)

StrategyPlugin: ``v2d_fade`` (fade-the-breakout, bracket-then-reverse, qty=1).
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import CLOCKS, session_bars
from .fx_v2b_london_ungated import (
    MARKETS,
    MarketSpec,
    _has_london_session,
    _regime_dates,
    _spread,
    _usd_norm,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "fx_v2d_london"
DEFAULT_START = date(2015, 1, 2)
LONDON = CLOCKS["london_open"]


def _progress(output_root: Path, message: str) -> None:
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    start: date,
    force: bool,
    max_days: Optional[int],
    entry_qty: int = 1,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
    regime_dates: Optional[List[date]] = None,
    session_frames: Optional[Dict[date, pd.DataFrame]] = None,
) -> dict:
    strategy_id = "%s_v2d_london_q%d" % (market.symbol.lower(), entry_qty)
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
        _progress(output_root, "LOAD %s 1m for v2d..." % market.symbol)
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    if regime_dates is None:
        regime_dates = _regime_dates(daily, gby, eff_start)
        regime_dates = [d for d in regime_dates if _has_london_session(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
    _progress(output_root, "  %s v2d sessions=%d" % (market.symbol, len(regime_dates)))

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "market": market.symbol.lower(),
        "entry_qty": entry_qty,
        "tick_size": market.tick,
        "rth_start": "03:00",
        "or_end": "03:15",
        "eod_cutoff": "11:59",
        "session_end": "12:00",
        "use_regime_filter": True,
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "regime_dates": [d.isoformat() for d in regime_dates],
        "record_levels": False,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2d_fade",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=max(1, entry_qty),
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
        extra={"driver": "fx_v2d_london"},
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
        "# FX / metals / CFD v2d fade — London session",
        "",
        "StrategyPlugin: `v2d_fade` (fade OR break via stop retest; qty=1).",
        "",
        "London clock (America/New_York):",
        "- OR **03:00–03:15**",
        "- Flatten **11:59**",
        "",
        "JPY pairs reported with native P&L and ≈USD via `/110`.",
        "",
        "| Rank | Symbol | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.3f |"
            % (
                i,
                r.get("symbol"),
                int(r.get("regime_days") or 0),
                int(r.get("trades") or 0),
                float(r.get("net_usd") or 0.0),
                float(r.get("stress_dd_usd") or 0.0),
                float(r.get("net_over_stress") or 0.0),
                100.0 * float(r.get("win_rate") or 0.0) if float(r.get("win_rate") or 0.0) <= 1.0 else float(r.get("win_rate") or 0.0),
                float(r.get("profit_factor") or 0.0),
            )
        )
    lines.extend(["", "Hub: `%s`" % output_root.as_posix().split("/potions/")[-1], ""])
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    email = [
        "potions: fx_v2d_london complete",
        "",
        "Hub: %s" % output_root,
        "Clock: London OR 03:00-03:15 / flatten 11:59",
        "Plugin: v2d_fade qty=1",
        "",
        "Ranked by N/S:",
    ]
    for i, r in enumerate(ranked[:12], start=1):
        email.append(
            "  %d. %s  net≈$%.0f  stress≈$%.0f  N/S=%.2f  trades=%d"
            % (
                i,
                r.get("symbol"),
                float(r.get("net_usd") or 0.0),
                float(r.get("stress_dd_usd") or 0.0),
                float(r.get("net_over_stress") or 0.0),
                int(r.get("trades") or 0),
            )
        )
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    markets: List[str],
    start: date,
    force: bool,
    max_days: Optional[int],
    email: bool,
    entry_qty: int = 1,
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
        "START london_open v2d_fade OR=03:00-03:15 eod=11:59 markets=%s"
        % ",".join(markets),
    )
    errors: List[str] = []
    for name in markets:
        key = name.upper()
        if key not in MARKETS:
            raise ValueError("Unknown market %s" % name)
        market = MARKETS[key]
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
        metrics_path = output_root / "states" / ("%s_v2d_london_q%d" % (key.lower(), entry_qty)) / "metrics.json"
        if (not force) and metrics_path.exists():
            _progress(output_root, "SKIP cached %s" % key)
            if key not in seen:
                row = json.loads(metrics_path.read_text(encoding="utf-8"))
                rows = [r for r in rows if str(r.get("symbol")) != key]
                rows.append(row)
                seen.add(key)
                write_summary(output_root, rows)
            continue
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
            _progress(output_root, "  %s london regime sessions=%d" % (key, len(regime_dates)))
            session_frames: Dict[date, pd.DataFrame] = {}
            for i, day in enumerate(regime_dates, start=1):
                session_frames[day] = session_bars(gby.get(day), day, LONDON, dense=True)
                if i % 500 == 0:
                    _progress(output_root, "  %s densify %d/%d" % (key, i, len(regime_dates)))
            row = run_one(
                output_root=output_root,
                market=market,
                start=start,
                force=force,
                max_days=max_days,
                entry_qty=entry_qty,
                gby=gby,
                regime_dates=regime_dates,
                session_frames=session_frames,
            )
            rows = [r for r in rows if str(r.get("symbol")) != key]
            rows.append(row)
            seen.add(key)
            write_summary(output_root, rows)
        except Exception as exc:
            tb = traceback.format_exc()
            errors.append("%s: %s" % (key, exc))
            _progress(output_root, "ERROR %s: %s" % (key, exc))
            (output_root / ("ERROR_%s.txt" % key)).write_text(tb, encoding="utf-8")
            write_summary(output_root, rows)

    write_summary(output_root, rows)
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "status": "COMPLETE" if not errors else "COMPLETE_WITH_ERRORS",
                "markets": markets,
                "errors": errors,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_v2d_london complete", body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="London-session v2d fade across FX/metals/CFDs.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument(
        "--markets",
        default=",".join(MARKETS.keys()),
        help="Comma list (default: all FX/metals/CFDs).",
    )
    parser.add_argument("--entry-qty", type=int, default=1)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--no-force", action="store_true", help="Reuse cached metrics.json when present.")
    parser.add_argument("--email", action="store_true", help="Email EMAIL.txt via Resend on finish.")
    args = parser.parse_args(argv)
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    rows = run_batch(
        output_root=args.output_root,
        markets=markets,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
        entry_qty=args.entry_qty,
    )
    print("Wrote %s (%d rows)" % (args.output_root / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
