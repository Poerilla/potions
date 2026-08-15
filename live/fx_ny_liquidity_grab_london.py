"""Broker-like NY liquidity-grab during London — FX + metals.

Plugin ``ny_liquidity_grab``: after London open (03:00 NY), wait until price
trades into the **prior NY RTH (09:30–15:59)** range, then rest OCO limits at
that high/low. First touch fills; risk = NY range; default TP at opposite
boundary (1R). Flatten 11:59.

Instruments: EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD.
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
from .fx_v2b_london_ungated import MARKETS, MarketSpec, REPO, _progress, _regime_dates, _spread, _usd_norm
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

DEFAULT_OUT = REPO / "live" / "state" / "fx_ny_liquidity_grab_london"
LONDON = CLOCKS["london_open"]
NY_RTH_START = time(9, 30)
NY_RTH_END = time(16, 0)
FX_METALS = ["EURUSD", "GBPUSD", "USDJPY", "AUDJPY", "XAUUSD", "XAGUSD"]


def _ny_rth_hilo(df: Optional[pd.DataFrame], session: date) -> Optional[Tuple[float, float]]:
    if df is None or df.empty:
        return None
    day = df[
        df.index.map(
            lambda ts: ts.date() == session and NY_RTH_START <= ts.time() < NY_RTH_END
        )
    ]
    if len(day) < 60:
        return None
    return float(day["high"].max()), float(day["low"].min())


def build_session_ny_ranges(gby: Dict[date, pd.DataFrame], sessions: Sequence[date]) -> Dict[str, dict]:
    """Map London session date → prior completed NY RTH high/low."""
    ny_by_day: Dict[date, Tuple[float, float]] = {}
    for day, frame in gby.items():
        hilo = _ny_rth_hilo(frame, day)
        if hilo is not None:
            ny_by_day[day] = hilo
    out: Dict[str, dict] = {}
    for session in sessions:
        prior = session - timedelta(days=1)
        while prior not in ny_by_day and prior >= session - timedelta(days=10):
            prior -= timedelta(days=1)
        if prior not in ny_by_day:
            continue
        high, low = ny_by_day[prior]
        out[session.isoformat()] = {
            "high": high,
            "low": low,
            "ny_session": prior.isoformat(),
            "range": high - low,
        }
    return out


def _has_london(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    raw = session_bars(raw_day, session, LONDON, dense=False)
    return (not raw.empty) and len(raw) >= max(40, LONDON.min_session_bars // 3)


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    start: date,
    force: bool,
    max_days: Optional[int],
    tp_r_mult: float,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
    regime_dates: Optional[List[date]] = None,
    session_frames: Optional[Dict[date, pd.DataFrame]] = None,
    session_ny_ranges: Optional[Dict[str, dict]] = None,
) -> dict:
    strategy_id = "%s_ny_liquidity_grab_london_1lot" % market.symbol.lower()
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

    if gby is None:
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    if regime_dates is None:
        regime_dates = [d for d in _regime_dates(daily, gby, eff_start) if _has_london(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
    if session_ny_ranges is None:
        session_ny_ranges = build_session_ny_ranges(gby, regime_dates)
    # Drop sessions without a prior NY range.
    regime_dates = [d for d in regime_dates if d.isoformat() in session_ny_ranges]

    _progress(output_root, "  %s sessions=%d ny_ranges=%d" % (market.symbol, len(regime_dates), len(session_ny_ranges)))
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": market.tick,
        "entry_qty": 1,
        "tp_r_mult": float(tp_r_mult),
        "rth_start": "03:00",
        "eod_cutoff": "11:59",
        "use_regime_filter": True,
        "regime_dates": [d.isoformat() for d in regime_dates],
        "session_ny_ranges": session_ny_ranges,
        "min_range_ticks": 10,
        "record_levels": False,
        "suppress_alerts": True,
        "start": eff_start.isoformat(),
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="ny_liquidity_grab",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=1,
                    max_open_orders=16,
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
        "entry_qty": 1,
        "tp_r_mult": float(tp_r_mult),
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
    # Strip bulky ranges from manifest config
    slim = {k: v for k, v in payload.items() if k != "session_ny_ranges"}
    slim["ny_range_sessions"] = len(session_ny_ranges)
    write_run_manifest(
        state_root,
        data_inputs=[one_m, daily],
        output_paths=[metrics_path, state_root / "fills.csv"],
        strategy_config=slim,
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": market.fee_per_unit},
        causality_mode="audit",
        extra={"driver": "fx_ny_liquidity_grab_london"},
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
        "# NY liquidity grab — London session (FX + metals)",
        "",
        "Plugin `ny_liquidity_grab`: after London open, arm OCO at prior NY RTH H/L once price trades into that range; 1 lot; risk=NY range; TP=1R opposite.",
        "Arm 03:00 window → flatten 11:59 America/New_York.",
        "",
        "| Rank | Symbol | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.3f |"
            % (
                i,
                r["symbol"],
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
        "potions: fx_ny_liquidity_grab_london complete",
        "",
        "London: wait for price into prior NY RTH range → OCO at H/L — 1 lot — risk=NY range — TP opposite (1R).",
        "",
        "Top by N/S:",
    ]
    for r in ranked:
        email.append(
            "  %s  N/S=%.2f  net≈$%.0f  trades=%d"
            % (r["symbol"], float(r["net_over_stress"]), float(r["net_usd"]), int(r["trades"]))
        )
    email.extend(["", "Hub: %s" % output_root])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    markets: Sequence[str],
    start: date,
    force: bool,
    max_days: Optional[int],
    tp_r_mult: float,
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
    _progress(output_root, "START ny_liquidity_grab markets=%s" % ",".join(markets))
    errors: List[str] = []
    for name in markets:
        key = name.upper()
        if key not in MARKETS:
            raise ValueError(key)
        market = MARKETS[key]
        sid = "%s_ny_liquidity_grab_london_1lot" % key.lower()
        mp = output_root / "states" / sid / "metrics.json"
        if (not force) and (key in seen or mp.exists()):
            if mp.exists() and key not in seen:
                rows.append(json.loads(mp.read_text(encoding="utf-8")))
                seen.add(key)
            write_summary(output_root, rows)
            continue
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        daily = REPO / "fx" / ("%s_daily.csv" % market.symbol.lower())
        try:
            _progress(output_root, "LOAD %s..." % key)
            gby = load_fx_1m_by_ny_date(one_m, market.symbol)
            regime_dates = [d for d in _regime_dates(daily, gby, start) if _has_london(gby.get(d), d)]
            if max_days is not None:
                regime_dates = regime_dates[:max_days]
            session_ny_ranges = build_session_ny_ranges(gby, regime_dates)
            regime_dates = [d for d in regime_dates if d.isoformat() in session_ny_ranges]
            session_frames = {d: session_bars(gby.get(d), d, LONDON, dense=True) for d in regime_dates}
            row = run_one(
                output_root=output_root,
                market=market,
                start=start,
                force=force,
                max_days=max_days,
                tp_r_mult=tp_r_mult,
                gby=gby,
                regime_dates=regime_dates,
                session_frames=session_frames,
                session_ny_ranges=session_ny_ranges,
            )
            rows = [r for r in rows if str(r.get("symbol")) != key]
            rows.append(row)
            seen.add(key)
            write_summary(output_root, rows)
        except Exception as exc:
            errors.append("%s: %s" % (key, exc))
            _progress(output_root, "ERROR %s: %s" % (key, exc))
            (output_root / ("ERROR_%s.txt" % key)).write_text(traceback.format_exc(), encoding="utf-8")
    write_summary(output_root, rows)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_ny_liquidity_grab_london complete", body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--start", default="2015-01-02")
    p.add_argument("--markets", default=",".join(FX_METALS))
    p.add_argument("--tp-r-mult", type=float, default=1.0)
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--no-force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    rows = run_batch(
        output_root=args.output_root,
        markets=[m.strip().upper() for m in args.markets.split(",") if m.strip()],
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        tp_r_mult=args.tp_r_mult,
        email=args.email,
    )
    print("Wrote %s (%d rows)" % (args.output_root / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
