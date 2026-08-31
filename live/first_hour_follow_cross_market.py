"""Broker-like Engine+PaperBroker: first-hour follow 3R, all days.

NY RTH first hour (09:30–10:30) on 5m tape. StrategyPlugin ``first_hour_follow``:
``market_close`` at last FH bar (10:25), SL = FH open, TP = 3× body, flatten 15:59.

Universe: NQ, ES, MES, YM, metals, FX, index CFDs. ES 1m/5m is often missing —
those rows are skipped, not failed.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.first_hour_follow_cross_market --email
  python -m live.first_hour_follow_cross_market --email --smoke
  python -m live.first_hour_follow_cross_market --email --markets MES,EURUSD
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "first_hour_follow_broker"
CACHE = REPO / "live" / "state" / "_cache" / "bars"
NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
JPY_USD = 110.0
FEE = 1.50


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    family: str  # futures | metal | fx | cfd
    tick: float
    point_value: float
    quote: str  # USD | JPY
    source: str  # rth_5m_csv | dbn_1m | fx_1m
    path: Path


MARKETS: Dict[str, MarketSpec] = {
    "NQ": MarketSpec("NQ", "futures", 0.25, 20.0, "USD", "rth_5m_csv", REPO / "nq" / "nq_5min_rth.csv"),
    "ES": MarketSpec(
        "ES",
        "futures",
        0.25,
        50.0,
        "USD",
        "dbn_1m",
        REPO / "es" / "raw" / "glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst",
    ),
    "MES": MarketSpec("MES", "futures", 0.25, 5.0, "USD", "rth_5m_csv", REPO / "mes" / "mes_5min_rth.csv"),
    "YM": MarketSpec(
        "YM",
        "futures",
        1.0,
        5.0,
        "USD",
        "dbn_1m",
        REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    ),
    "XAUUSD": MarketSpec("XAUUSD", "metal", 0.01, 100.0, "USD", "fx_1m", REPO / "fx" / "xauusd_1m.csv"),
    "XAGUSD": MarketSpec("XAGUSD", "metal", 0.001, 1000.0, "USD", "fx_1m", REPO / "fx" / "xagusd_1m.csv"),
    "EURUSD": MarketSpec("EURUSD", "fx", 0.00001, 100_000.0, "USD", "fx_1m", REPO / "fx" / "eurusd_1m.csv"),
    "GBPUSD": MarketSpec("GBPUSD", "fx", 0.00001, 100_000.0, "USD", "fx_1m", REPO / "fx" / "gbpusd_1m.csv"),
    "USDJPY": MarketSpec("USDJPY", "fx", 0.001, 100_000.0, "JPY", "fx_1m", REPO / "fx" / "usdjpy_1m.csv"),
    "AUDJPY": MarketSpec("AUDJPY", "fx", 0.001, 100_000.0, "JPY", "fx_1m", REPO / "fx" / "audjpy_1m.csv"),
    "US30": MarketSpec("US30", "cfd", 0.1, 1.0, "USD", "fx_1m", REPO / "fx" / "us30_1m.csv"),
    "NAS100": MarketSpec("NAS100", "cfd", 0.1, 1.0, "USD", "fx_1m", REPO / "fx" / "nas100_1m.csv"),
}

DEFAULT_SYMBOLS: Tuple[str, ...] = tuple(MARKETS.keys())


def _usd_norm(value: float, quote: str) -> float:
    return value / JPY_USD if quote == "JPY" else value


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _spread(tick: float, family: str) -> SpreadModel:
    if family == "fx":
        return SpreadModel(
            rth_half_spread_ticks=0.5,
            eth_half_spread_ticks=5.0,
            open_widen_half_spread_ticks=1.0,
            low_volume_threshold=50.0,
            low_volume_multiplier=1.5,
            tick_size=tick,
        )
    return SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0 if family != "cfd" else 1.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def _ensure_ny(ts: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(ts, utc=True, errors="coerce")
    if parsed.isna().any():
        parsed = pd.to_datetime(ts, errors="coerce")
        if getattr(parsed.dt, "tz", None) is None:
            parsed = parsed.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            parsed = parsed.dt.tz_convert(NY)
    else:
        parsed = parsed.dt.tz_convert(NY)
    return parsed


def _ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    if "ts" not in df.columns:
        if "ts_event" in df.columns:
            df = df.rename(columns={"ts_event": "ts"})
        elif pd.api.types.is_datetime64_any_dtype(df.index):
            df = df.reset_index()
            first = df.columns[0]
            df = df.rename(columns={first: "ts"})
        else:
            raise ValueError("no timestamp column")
    vol = df["volume"] if "volume" in df.columns else 0.0
    out = pd.DataFrame(
        {
            "ts": _ensure_ny(df["ts"]),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(vol, errors="coerce").fillna(0.0),
        }
    ).dropna(subset=["ts", "open", "high", "low", "close"])
    return out.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


def _filter_rth(df: pd.DataFrame) -> pd.DataFrame:
    t = df["ts"].dt.tz_convert(NY).dt.time
    wd = df["ts"].dt.dayofweek
    return df[(t >= RTH_OPEN) & (t < RTH_CLOSE) & (wd < 5)].copy()


def _resample_5m(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    g = df.set_index("ts").sort_index()
    ohlc = g.resample("5min", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    out = ohlc.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return _filter_rth(out)


def _cache_path(symbol: str) -> Path:
    return CACHE / ("%s_5m_rth.parquet" % symbol.lower())


def _load_rth_5m_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return _filter_rth(_ohlcv_frame(df))


def _load_fx_1m_rth_5m(path: Path, symbol: str, hub: Path) -> pd.DataFrame:
    _progress(hub, "  resample %s 1m → RTH 5m ..." % symbol)
    usecols = lambda c: c in {"ts_event", "ts", "open", "high", "low", "close", "volume"}
    chunks: List[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=400_000):
        chunks.append(_filter_rth(_ohlcv_frame(chunk)))
    if not chunks:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    one = pd.concat(chunks, ignore_index=True).sort_values("ts").drop_duplicates("ts", keep="last")
    return _resample_5m(one)


def _load_dbn_rth_5m(path: Path, symbol: str, hub: Path) -> pd.DataFrame:
    from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

    _progress(hub, "  load %s 1m DBN → RTH 5m ..." % symbol)
    gby = load_1m_by_ny_date_any(path.resolve(), symbol.lower())
    parts: List[pd.DataFrame] = []
    for day_df in gby.values():
        if day_df is None or day_df.empty:
            continue
        parts.append(_filter_rth(_ohlcv_frame(day_df.reset_index())))
    if not parts:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    one = pd.concat(parts, ignore_index=True).sort_values("ts").drop_duplicates("ts", keep="last")
    return _resample_5m(one)


def load_market_5m(market: MarketSpec, hub: Path) -> pd.DataFrame:
    cache = _cache_path(market.symbol)
    if cache.exists():
        df = pd.read_parquet(cache)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
        df = _filter_rth(_ohlcv_frame(df))
        if len(df) >= 200:
            _progress(hub, "CACHE 5m %s bars=%s" % (market.symbol, f"{len(df):,}"))
            return df.reset_index(drop=True)

    if market.source == "rth_5m_csv":
        if not market.path.exists():
            raise FileNotFoundError(market.path)
        df = _load_rth_5m_csv(market.path)
    elif market.source == "fx_1m":
        if not market.path.exists():
            raise FileNotFoundError(market.path)
        df = _load_fx_1m_rth_5m(market.path, market.symbol, hub)
    elif market.source == "dbn_1m":
        if not market.path.exists():
            raise FileNotFoundError(market.path)
        df = _load_dbn_rth_5m(market.path, market.symbol, hub)
    else:
        raise ValueError("unknown source %s" % market.source)

    CACHE.mkdir(parents=True, exist_ok=True)
    df.reset_index(drop=True).to_parquet(cache, index=False)
    _progress(hub, "  cached %s rows=%s" % (cache.name, f"{len(df):,}"))
    return df.reset_index(drop=True)


def missing_reason(market: MarketSpec) -> Optional[str]:
    if market.path.exists():
        return None
    if market.symbol == "ES":
        return "ES 1m DBN missing locally (daily only)"
    return "missing data file %s" % market.path


def run_market(
    *,
    hub: Path,
    market: MarketSpec,
    df: pd.DataFrame,
    force: bool,
) -> dict:
    strategy_id = "%s_fh_follow_3r_all" % market.symbol.lower()
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(hub, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": market.tick,
        "entry_qty": 1,
        "r_mult": 3.0,
        "fade": False,
        "fh_start": "09:30",
        "fh_end": "10:30",
        "bar_minutes": 5,
        "eod_cutoff": "15:59",
        "min_fh_bars": 10,
        "require_fh_body": "",
        "strong_body_min": 0.66,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="first_hour_follow",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="5m",
                    max_contracts=8,
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
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=_spread(market.tick, market.family)),
    )

    _progress(hub, "RUN %s bars=%s" % (strategy_id, f"{len(df):,}"))
    audit_bars: List[AuditBar] = []
    n = 0
    source = str(market.path)
    for row in df.itertuples(index=False):
        ts = pd.Timestamp(row.ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize(NY)
        else:
            ts = ts.tz_convert(NY)
        ts_s = ts.strftime("%Y-%m-%dT%H:%M:%S")
        bar = Bar(
            instrument=market.symbol,
            timeframe="5m",
            ts=ts_s,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(getattr(row, "volume", 0.0) or 0.0),
            complete=True,
            source=source,
        )
        engine.process_bar(bar)
        audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        n += 1
        if n % 50000 == 0:
            _progress(hub, "  %s %d/%d" % (strategy_id, n, len(df)))
    store.flush_tables()

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.symbol,
        fee_per_unit=FEE,
    )
    net_native = float(audit.get("net_usd") or 0.0)
    stress_native = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    closed_native = float(audit.get("closed_dd_usd") or 0.0)
    net = _usd_norm(net_native, market.quote)
    stress = _usd_norm(stress_native, market.quote)
    closed = _usd_norm(closed_native, market.quote)
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    wr = float(audit.get("win_rate") or 0.0)
    if wr > 1.0:
        wr = wr / 100.0
    first = pd.Timestamp(df["ts"].iloc[0]).tz_convert(NY).date().isoformat() if len(df) else ""
    last = pd.Timestamp(df["ts"].iloc[-1]).tz_convert(NY).date().isoformat() if len(df) else ""
    metrics = {
        "strategy_id": strategy_id,
        "symbol": market.symbol,
        "family": market.family,
        "quote": market.quote,
        "skipped": False,
        "skip_reason": "",
        "bars": len(audit_bars),
        "sessions": int(df["ts"].dt.tz_convert(NY).dt.date.nunique()) if len(df) else 0,
        "first_session": first,
        "last_session": last,
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "win_rate": wr,
        "net_native": net_native,
        "intrabar_stress_dd_native": stress_native,
        "net_usd": net,
        "closed_dd_usd": closed,
        "intrabar_stress_dd_usd": stress,
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "config": payload,
        "data_path": str(market.path),
    }
    state_root.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
        % (market.symbol, trades, wr * 100.0, net, stress, metrics["net_over_stress"]),
    )
    return metrics


def skipped_row(market: MarketSpec, reason: str) -> dict:
    return {
        "strategy_id": "%s_fh_follow_3r_all" % market.symbol.lower(),
        "symbol": market.symbol,
        "family": market.family,
        "quote": market.quote,
        "skipped": True,
        "skip_reason": reason,
        "bars": 0,
        "sessions": 0,
        "first_session": "",
        "last_session": "",
        "units": 0,
        "trades": 0,
        "win_rate": 0.0,
        "net_native": 0.0,
        "intrabar_stress_dd_native": 0.0,
        "net_usd": 0.0,
        "closed_dd_usd": 0.0,
        "intrabar_stress_dd_usd": 0.0,
        "net_over_stress": 0.0,
        "max_open_units": 0,
        "profit_factor": 0.0,
        "config": {},
        "data_path": str(market.path),
    }


def write_summary(hub: Path, results: List[dict], skipped: List[dict]) -> Path:
    ran = [r for r in results if not r.get("skipped")]
    ranked = sorted(ran, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    lines = [
        "# First-hour follow 3R all days (broker-like)",
        "",
        "Engine + PaperBroker + StrategyPlugin `first_hour_follow` on NY RTH 5m.",
        "Book: **follow 3R, every directional first hour** (09:30–10:30). "
        "Entry `market_close` on last FH bar (10:25); SL = FH open; TP = 3× body; flatten 15:59.",
        "Realism: slip 1 tick, spread model, fee $1.50/unit. JPY pairs ÷110 for USD.",
        "",
        "| Rank | Market | Family | Sessions | Trades | WR | Net USD | Stress DD | N/S | Window |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| {rank} | {sym} | {fam} | {sess} | {tr} | {wr:.1f}% | ${net:,.0f} | ${st:,.0f} | {ns:.2f} | {a} → {b} |".format(
                rank=i,
                sym=r["symbol"],
                fam=r["family"],
                sess=int(r.get("sessions") or 0),
                tr=int(r["trades"]),
                wr=100.0 * float(r["win_rate"]),
                net=float(r["net_usd"]),
                st=float(r["intrabar_stress_dd_usd"]),
                ns=float(r["net_over_stress"]),
                a=r.get("first_session") or "—",
                b=r.get("last_session") or "—",
            )
        )
    if skipped:
        lines.extend(["", "## Skipped", ""])
        for r in skipped:
            lines.append("- **%s**: %s" % (r["symbol"], r.get("skip_reason") or "unavailable"))
    lines.extend(
        [
            "",
            "## Stance",
            "",
            "Research / diagnostic. Same large first-hour-open stop as the NQ pandas mill. "
            "Do not promote from this table alone; compare N/S and WR vs the NQ broker-like "
            "hub `live/state/nq_1h_first_hour_broker/` (all-days N/S 5.57).",
            "",
            "Hub: `%s`" % hub,
            "",
        ]
    )
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results + skipped).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict], skipped: List[dict]) -> Path:
    ran = [r for r in results if not r.get("skipped")]
    ranked = sorted(ran, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    lines = [
        "First-hour follow 3R all-days broker-like complete",
        "Hub: %s" % hub,
        "Book: follow 3R every NY first hour (09:30–10:30) via StrategyPlugin first_hour_follow",
        "",
    ]
    for r in ranked:
        lines.append(
            "%s (%s): trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
            % (
                r["symbol"],
                r["family"],
                int(r["trades"]),
                100.0 * float(r["win_rate"]),
                float(r["net_usd"]),
                float(r["intrabar_stress_dd_usd"]),
                float(r["net_over_stress"]),
            )
        )
    if skipped:
        lines.append("")
        lines.append("Skipped: " + ", ".join("%s (%s)" % (r["symbol"], r["skip_reason"]) for r in skipped))
    best = ranked[0] if ranked else None
    if best:
        lines.extend(
            [
                "",
                "Lead N/S: %s %.2f. Diagnostic — large FH-open stop; do not promote from this pass alone."
                % (best["symbol"], float(best["net_over_stress"])),
            ]
        )
    lines.append("")
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="Last ~2y of RTH 5m per market")
    ap.add_argument(
        "--markets",
        default="",
        help="Comma list (default: NQ,ES,MES,YM + metals/FX/CFDs)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = args.out
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    wanted = [s.strip().upper() for s in (args.markets or ",".join(DEFAULT_SYMBOLS)).split(",") if s.strip()]
    unknown = [s for s in wanted if s not in MARKETS]
    if unknown:
        raise SystemExit("Unknown markets %s (want %s)" % (",".join(unknown), ",".join(MARKETS)))

    try:
        _progress(hub, "START first-hour follow 3R all-days markets=%s smoke=%s" % (",".join(wanted), args.smoke))
        results: List[dict] = []
        skipped: List[dict] = []
        data_inputs: List[Path] = []
        for sym in wanted:
            market = MARKETS[sym]
            reason = missing_reason(market)
            if reason:
                _progress(hub, "SKIP %s: %s" % (sym, reason))
                skipped.append(skipped_row(market, reason))
                continue
            try:
                df = load_market_5m(market, hub)
            except FileNotFoundError as exc:
                reason = str(exc)
                _progress(hub, "SKIP %s: %s" % (sym, reason))
                skipped.append(skipped_row(market, reason))
                continue
            if df.empty or len(df) < 200:
                reason = "too few RTH 5m bars (%d)" % len(df)
                _progress(hub, "SKIP %s: %s" % (sym, reason))
                skipped.append(skipped_row(market, reason))
                continue
            if args.smoke:
                cut = pd.Timestamp(df["ts"].max()).tz_convert(NY) - pd.Timedelta(days=500)
                df = df[df["ts"] >= cut].reset_index(drop=True)
                _progress(hub, "SMOKE %s bars=%d from %s" % (sym, len(df), cut.date()))
            data_inputs.append(market.path)
            results.append(run_market(hub=hub, market=market, df=df, force=args.force))
            write_summary(hub, results, skipped)

        write_summary(hub, results, skipped)
        email_path = write_email(hub, results, skipped)
        write_run_manifest(
            hub,
            data_inputs=data_inputs,
            strategy_config={
                "strategy_type": "first_hour_follow",
                "book": "follow_3r_all",
                "markets": wanted,
            },
            broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE},
            extra={"results": results, "skipped": skipped, "smoke": bool(args.smoke)},
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "results": results, "skipped": skipped}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: first-hour follow 3R all-days broker-like complete",
                body=email_path.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(hub, "FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text(
            "First-hour follow cross-market FAILED\nHub: %s\n\n%s\n" % (hub, tb),
            encoding="utf-8",
        )
        try:
            send_email(
                subject="potions: first-hour follow 3R all-days broker FAILED",
                body=fail.read_text(encoding="utf-8"),
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
