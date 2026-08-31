"""v2b S_1_1_3 gated by quarterly ATR4 fade-ladder bias (best path per market).

While the best-path fade trade is open, London v2b may arm **only** in that
trade's direction (Long after lower fade / Short after upper fade). When the
fade is flat, v2b does not fire at all.

Uses ``use_session_direction_bias`` + ``regime_dates`` = NY sessions overlapping
an open fade position (intersected with the usual MA50>MA150 regime when
available).
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import CLOCKS, session_bars
from .fx_v2b_london_ungated import (
    MARKETS as LONDON_MARKETS,
    MarketSpec,
    _has_london_session,
    _regime_dates,
    _spread,
    _usd_norm,
    resolve_book,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BEST_PATH = REPO / "live" / "state" / "quarterly_atr4_opposite_path" / "best_path.csv"
DEFAULT_LADDER_HUB = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_best_path"
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_fade_v2b_bias"
DEFAULT_START = date(2015, 1, 2)
LONDON = CLOCKS["london_open"]
NY = "America/New_York"

# Futures use RTH midnight-OR v2b (same plugin, different clock than London FX).
FUTURES_SPECS = {
    "NQ": {
        "tick": 0.25,
        "point_value": 20.0,
        "fee_per_unit": 1.50,
        "daily": REPO / "nq" / "nq_daily.csv",
        "dbn": REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
        "market_key": "nq",
    },
    "YM": {
        "tick": 1.0,
        "point_value": 5.0,
        "fee_per_unit": 1.50,
        "daily": REPO / "ym" / "ym_daily.csv",
        "dbn": REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
        "market_key": "ym",
    },
}


def _progress(output_root: Path, message: str) -> None:
    line = "[%s] %s" % (datetime.now().isoformat(timespec="seconds"), message)
    print(line, flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _parse_ts(raw) -> pd.Timestamp:
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").tz_convert(NY)
    return ts.tz_convert(NY)


def fade_bias_from_fills(fills_path: Path) -> Tuple[Dict[str, str], List[dict]]:
    """Map NY session ISO date → Long/Short while any fade trade is open."""
    if not fills_path.exists():
        return {}, []
    fills = pd.read_csv(fills_path)
    if fills.empty:
        return {}, []
    fills = fills.copy()
    fills["ts_ny"] = fills["ts"].map(_parse_ts)
    bias: Dict[str, str] = {}
    rows: List[dict] = []
    for trade_id, g in fills.groupby("trade_id", sort=True):
        g = g.sort_values("ts_ny")
        entry = g[g["reason"] == "entry"]
        if entry.empty:
            continue
        e = entry.iloc[0]
        exits = g[g["reason"] != "entry"]
        exit_ts = exits["ts_ny"].iloc[-1] if not exits.empty else e["ts_ny"]
        direction = "Long" if str(e["side"]).lower() == "buy" else "Short"
        # Inclusive NY calendar days with any overlap of [entry, exit].
        d0 = e["ts_ny"].tz_convert(NY).date()
        d1 = exit_ts.tz_convert(NY).date()
        cur = d0
        while cur <= d1:
            key = cur.isoformat()
            # Later trades overwrite same-day if overlapping (rare).
            bias[key] = direction
            rows.append(
                {
                    "session": key,
                    "trade_id": trade_id,
                    "direction": direction,
                    "entry_ts": e["ts_ny"].isoformat(),
                    "exit_ts": exit_ts.isoformat(),
                }
            )
            cur = cur + timedelta(days=1)
    return bias, rows


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    book: str,
    start: date,
    force: bool,
    bias_map: Dict[str, str],
    path_meta: dict,
    max_days: Optional[int] = None,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
) -> dict:
    sizing = resolve_book(book)
    entry_qty = sizing["entry_qty"]
    tp1_qty = sizing["tp1_qty"]
    tp2_qty = sizing["tp2_qty"]
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    strategy_id = "%s_v2b_fade_bias_%s" % (market.symbol.lower(), book)
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
    # Honour explicit --start so CFD fade history (pre-2021) can gate v2b.
    eff_start = start

    if gby is None:
        _progress(output_root, "LOAD %s 1m..." % market.symbol)
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)

    # Eligible = fade-open sessions ∩ MA regime ∩ London session present.
    regime = set(_regime_dates(daily, gby, eff_start))
    bias_days = []
    for s, side in sorted(bias_map.items()):
        d = date.fromisoformat(s)
        if d < eff_start or d not in regime:
            continue
        if side not in {"Long", "Short"}:
            continue
        if not _has_london_session(gby.get(d), d):
            continue
        bias_days.append(d)
    if max_days is not None:
        bias_days = bias_days[:max_days]

    session_bias = {d.isoformat(): bias_map[d.isoformat()] for d in bias_days}
    long_n = sum(1 for d in bias_days if session_bias[d.isoformat()] == "Long")
    short_n = sum(1 for d in bias_days if session_bias[d.isoformat()] == "Short")
    _progress(
        output_root,
        "  %s path=%s fade_sessions=%d (Long=%d Short=%d) book=%s"
        % (market.symbol, path_meta.get("path_id"), len(bias_days), long_n, short_n, book),
    )

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
        "use_session_direction_bias": True,
        "session_direction_bias": session_bias,
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "regime_dates": [d.isoformat() for d in bias_days],
        "fade_path_id": path_meta.get("path_id"),
        "fade_trade_mode": path_meta.get("trade_mode"),
        "fade_risk_atr_mult": path_meta.get("risk_atr_mult"),
        "record_levels": False,
        "suppress_alerts": True,
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
    for idx, day in enumerate(bias_days, start=1):
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
        if idx % 100 == 0:
            _progress(output_root, "  %s %d/%d" % (strategy_id, idx, len(bias_days)))

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
    result = {
        "strategy_id": strategy_id,
        "symbol": market.symbol,
        "family": market.family,
        "quote": market.quote,
        "book": book,
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "path_id": path_meta.get("path_id"),
        "trade_mode": path_meta.get("trade_mode"),
        "path_win_rate": path_meta.get("win_rate"),
        "risk_atr_mult": path_meta.get("risk_atr_mult"),
        "fade_bias_sessions": len(bias_days),
        "fade_bias_long_sessions": long_n,
        "fade_bias_short_sessions": short_n,
        "start": eff_start.isoformat(),
        "clock": "london_open",
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
        "net_usd": _usd_norm(net, market.quote),
        "closed_dd_usd": _usd_norm(closed, market.quote),
        "stress_dd_usd": _usd_norm(stress, market.quote),
        "net_over_stress": (_usd_norm(net, market.quote) / abs(_usd_norm(stress, market.quote)))
        if stress
        else 0.0,
        "win_rate": float(audit.get("win_rate") or 0.0),
    }
    state_root.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d units=%d sessions=%d"
        % (
            market.symbol,
            result["net_usd"],
            result["net_over_stress"],
            result["trades"],
            result["units"],
            result["fade_bias_sessions"],
        ),
    )
    return result


def _futures_regime_dates(daily_path: Path, gby: Dict[date, pd.DataFrame], start: date) -> List[date]:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    daily["ma50"] = pd.to_numeric(daily["close"], errors="coerce").rolling(50).mean()
    daily["ma150"] = pd.to_numeric(daily["close"], errors="coerce").rolling(150).mean()
    daily["eligible"] = (daily["ma50"] > daily["ma150"]).shift(1).fillna(False)
    eligible = {pd.Timestamp(row["date"]).date() for _, row in daily[daily["eligible"]].iterrows()}
    out = []
    for day in sorted(gby):
        if day < start or day not in eligible:
            continue
        raw = gby.get(day)
        if raw is None or raw.empty:
            continue
        if rth_bars(raw, day, dense=False).empty:
            continue
        out.append(day)
    return out


def run_one_futures(
    *,
    output_root: Path,
    symbol: str,
    book: str,
    start: date,
    force: bool,
    bias_map: Dict[str, str],
    path_meta: dict,
    max_days: Optional[int] = None,
) -> dict:
    """RTH midnight-OR v2b S_1_1_3 gated by fade bias (NQ/YM)."""
    import sys

    spec = FUTURES_SPECS[symbol.upper()]
    sizing = resolve_book(book)
    entry_qty = sizing["entry_qty"]
    tp1_qty = sizing["tp1_qty"]
    tp2_qty = sizing["tp2_qty"]
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    strategy_id = "%s_v2b_fade_bias_%s" % (symbol.lower(), book)
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[symbol] = float(spec["point_value"])
    DEFAULT_TICK_SIZE[symbol] = float(spec["tick"])

    # Lazy import — heavy mnq chart helpers.
    mnq_root = REPO / "mnq"
    case = mnq_root / "case_studies" / "midnight_open_hourly_charts"
    scripts = REPO / "scripts"
    sys.path[:0] = [str(mnq_root), str(scripts), str(case)]
    import build_midnight_open_hourly_charts as mdata  # noqa: WPS433

    _progress(output_root, "LOAD %s 1m DBN..." % symbol)
    gby = mdata.load_1m_by_ny_date(Path(spec["dbn"]).resolve(), str(spec["market_key"]))
    regime = set(_futures_regime_dates(Path(spec["daily"]), gby, start))
    bias_days = []
    for s, side in sorted(bias_map.items()):
        d = date.fromisoformat(s)
        if d < start or d not in regime:
            continue
        if side not in {"Long", "Short"}:
            continue
        bias_days.append(d)
    if max_days is not None:
        bias_days = bias_days[:max_days]

    session_bias = {d.isoformat(): bias_map[d.isoformat()] for d in bias_days}
    long_n = sum(1 for d in bias_days if session_bias[d.isoformat()] == "Long")
    short_n = sum(1 for d in bias_days if session_bias[d.isoformat()] == "Short")
    _progress(
        output_root,
        "  %s path=%s fade_sessions=%d (Long=%d Short=%d) book=%s clock=rth"
        % (symbol, path_meta.get("path_id"), len(bias_days), long_n, short_n, book),
    )

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "market": str(spec["market_key"]),
        "mode": "oco_then_reverse",
        "entry_qty": entry_qty,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "tick_size": float(spec["tick"]),
        "use_regime_filter": True,
        "prior_opposite_only": False,
        "use_session_direction_bias": True,
        "session_direction_bias": session_bias,
        "start": start.isoformat(),
        "clock": "rth",
        "regime_dates": [d.isoformat() for d in bias_days],
        "fade_path_id": path_meta.get("path_id"),
        "fade_trade_mode": path_meta.get("trade_mode"),
        "fade_risk_atr_mult": path_meta.get("risk_atr_mult"),
        "record_levels": False,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2b_scaleout",
                    version="v1",
                    instrument=symbol,
                    broker_instrument=symbol,
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
        tick_size={symbol: float(spec["tick"])},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0),
    )
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(bias_days, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df is None or df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=symbol,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(spec["dbn"]),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 50 == 0:
            _progress(output_root, "  %s %d/%d" % (strategy_id, idx, len(bias_days)))

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=symbol,
        fee_per_unit=float(spec["fee_per_unit"]),
    )
    net = float(audit["net_usd"])
    stress = float(audit["intrabar_stress_dd_usd"])
    closed = float(audit["closed_dd_usd"])
    result = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "family": "futures",
        "quote": "USD",
        "book": book,
        "sizing": "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner),
        "path_id": path_meta.get("path_id"),
        "trade_mode": path_meta.get("trade_mode"),
        "path_win_rate": path_meta.get("win_rate"),
        "risk_atr_mult": path_meta.get("risk_atr_mult"),
        "fade_bias_sessions": len(bias_days),
        "fade_bias_long_sessions": long_n,
        "fade_bias_short_sessions": short_n,
        "start": start.isoformat(),
        "clock": "rth",
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
        "net_usd": net,
        "closed_dd_usd": closed,
        "stress_dd_usd": stress,
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "win_rate": float(audit.get("win_rate") or 0.0),
    }
    state_root.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d units=%d sessions=%d"
        % (symbol, net, result["net_over_stress"], result["trades"], result["units"], len(bias_days)),
    )
    return result


def write_summary(output_root: Path, rows: Sequence[dict]) -> None:
    df = pd.DataFrame(list(rows))
    df.to_csv(output_root / "summary.csv", index=False)
    lines = [
        "# Quarterly ATR4 fade → v2b S_1_1_3 bias",
        "",
        "v2b London S_1_1_3 arms **only** on sessions where the market's best-path",
        "quarterly fade ladder trade is open, and **only** in that trade's direction.",
        "",
        "| Market | Path | Path WR | Bias sess | Trades | Units | Net USD | Stress | N/S | WR |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            "| %s | %s | %.1f%% | %d | %d | %d | %+.0f | %.0f | %.2f | %.1f%% |"
            % (
                r["symbol"],
                r.get("path_id"),
                100.0 * float(r.get("path_win_rate") or 0.0),
                int(r.get("fade_bias_sessions") or 0),
                int(r.get("trades") or 0),
                int(r.get("units") or 0),
                float(r.get("net_usd") or 0.0),
                float(r.get("stress_dd_usd") or 0.0),
                float(r.get("net_over_stress") or 0.0),
                float(r.get("win_rate") or 0.0),
            )
        )
    lines.extend(
        [
            "",
            "Hub: `%s`" % output_root,
            "Bias maps: `bias/<symbol>_fade_bias_by_session.csv`",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = "\n".join(
        [
            "potions: quarterly ATR4 fade → v2b S_1_1_3 bias complete",
            "",
            "Hub: %s" % output_root,
            "Markets: %d" % len(df),
            "",
            (output_root / "SUMMARY.md").read_text(encoding="utf-8"),
        ]
    )
    (output_root / "EMAIL.txt").write_text(email, encoding="utf-8")


def run(
    *,
    output_root: Path,
    best_path: Path,
    ladder_hub: Path,
    book: str,
    start: date,
    force: bool,
    email: bool,
    symbols: Optional[Sequence[str]] = None,
    max_days: Optional[int] = None,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    bp = pd.read_csv(best_path)
    bias_dir = output_root / "bias"
    bias_dir.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    try:
        for _, prow in bp.iterrows():
            sym = str(prow["market"]).upper()
            if symbols is not None and sym not in {s.upper() for s in symbols}:
                continue
            fills = (
                ladder_hub
                / "states"
                / ("%s_quarterly_atr4_fade_ladder" % sym.lower())
                / "fills.csv"
            )
            bias_map, bias_rows = fade_bias_from_fills(fills)
            pd.DataFrame(bias_rows).to_csv(
                bias_dir / ("%s_fade_bias_by_session.csv" % sym.lower()), index=False
            )
            path_meta = {
                "path_id": prow.get("path_id"),
                "trade_mode": prow.get("trade_mode"),
                "win_rate": float(prow.get("win_rate") or 0.0),
                "risk_atr_mult": float(prow.get("risk_atr_mult") or 0.0),
            }
            if not bias_map:
                _progress(output_root, "SKIP %s — no fade fills at %s" % (sym, fills))
                continue
            if sym in LONDON_MARKETS:
                rows.append(
                    run_one(
                        output_root=output_root,
                        market=LONDON_MARKETS[sym],
                        book=book,
                        start=start,
                        force=force,
                        bias_map=bias_map,
                        path_meta=path_meta,
                        max_days=max_days,
                    )
                )
            elif sym in FUTURES_SPECS:
                rows.append(
                    run_one_futures(
                        output_root=output_root,
                        symbol=sym,
                        book=book,
                        start=start,
                        force=force,
                        bias_map=bias_map,
                        path_meta=path_meta,
                        max_days=max_days,
                    )
                )
            else:
                _progress(output_root, "SKIP %s (no v2b 1m book)" % sym)
                continue
        write_summary(output_root, rows)
        write_run_manifest(
            output_root,
            data_inputs=[best_path, ladder_hub],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={"plugin": "v2b_scaleout", "book": book, "gate": "fade_bias"},
            broker_realism_config={"slippage_ticks": 1.0},
            extra={"markets": [r["symbol"] for r in rows]},
        )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "markets": [r["symbol"] for r in rows]}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: quarterly ATR4 fade → v2b bias FAILED\n\nHub: %s\n\n%s\n"
            % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: quarterly ATR4 fade → v2b bias FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise
    if email:
        send_email(
            subject="potions: quarterly ATR4 fade → v2b S_1_1_3 bias complete",
            body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress(output_root, "email sent")
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--best-path", type=Path, default=DEFAULT_BEST_PATH)
    ap.add_argument("--ladder-hub", type=Path, default=DEFAULT_LADDER_HUB)
    ap.add_argument("--book", default="S_1_1_3")
    ap.add_argument("--start", default=DEFAULT_START.isoformat())
    ap.add_argument("--symbol", action="append", default=None)
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(
        output_root=args.output_root,
        best_path=args.best_path,
        ladder_hub=args.ladder_hub,
        book=args.book,
        start=date.fromisoformat(args.start),
        force=args.force,
        email=args.email,
        symbols=args.symbol,
        max_days=args.max_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
