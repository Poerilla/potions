"""Broker-like Engine+PaperBroker replay: quarterly ±4×ATR first-touch fade.

Markets: GBPUSD, US30, NAS100 on 4h bars (same levels as quarterly chart study).

Rules (StrategyPlugin ``quarterly_atr4_fade``):
  - Open-week H/L/mid + ATR(14) at week close → mid ±4×ATR
  - First touch upper → short 2; first touch lower → long 2
  - Risk 0.5× open-week range; TP1 1@mid; runner 1@opposite ±4×ATR
  - Runner fill → reverse once; max 2 trades/quarter; flatten at quarter end
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
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
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_fade_broker"
NY = "America/New_York"


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    tick: float
    point_value: float
    fee_per_unit: float
    csv: Path
    family: str  # fx | metal | cfd | futures
    source_1h: Optional[Path] = None  # optional parquet/csv to build 4h


CACHE_1H = REPO / "live" / "state" / "_cache" / "bars"
DERIVED_4H = REPO / "live" / "state" / "_cache" / "bars_4h"


def _spec(
    symbol: str,
    tick: float,
    point_value: float,
    fee: float,
    family: str,
    csv: Path,
    source_1h: Optional[Path] = None,
) -> MarketSpec:
    return MarketSpec(symbol, tick, point_value, fee, csv, family, source_1h)


MARKETS: Dict[str, MarketSpec] = {
    # FX
    "EURUSD": _spec(
        "EURUSD", 0.00001, 100_000.0, 1.50, "fx",
        DERIVED_4H / "eurusd_4h.csv", CACHE_1H / "eurusd_1h.parquet",
    ),
    "GBPUSD": _spec("GBPUSD", 0.00001, 100_000.0, 7.0, "fx", REPO / "fx" / "gbpusd_4h.csv"),
    "USDJPY": _spec("USDJPY", 0.001, 100_000.0, 1.50, "fx", REPO / "fx" / "usdjpy_4h.csv"),
    "AUDJPY": _spec("AUDJPY", 0.001, 100_000.0, 1.50, "fx", REPO / "fx" / "audjpy_4h.csv"),
    # Metals
    "XAUUSD": _spec("XAUUSD", 0.01, 100.0, 1.50, "metal", REPO / "fx" / "xauusd_4h.csv"),
    "XAGUSD": _spec("XAGUSD", 0.001, 1000.0, 1.50, "metal", REPO / "fx" / "xagusd_4h.csv"),
    # Index CFDs
    "US30": _spec("US30", 0.1, 1.0, 1.50, "cfd", REPO / "fx" / "us30_4h.csv"),
    "NAS100": _spec("NAS100", 0.1, 1.0, 1.50, "cfd", REPO / "fx" / "nas100_4h.csv"),
    "SPX500": _spec("SPX500", 0.1, 1.0, 1.50, "cfd", REPO / "fx" / "spx500_4h.csv"),
    # Futures (4h derived from cached 1h)
    "NQ": _spec(
        "NQ", 0.25, 20.0, 1.50, "futures",
        DERIVED_4H / "nq_4h.csv", CACHE_1H / "nq_1h.parquet",
    ),
    "MNQ": _spec(
        "MNQ", 0.25, 2.0, 1.50, "futures",
        DERIVED_4H / "mnq_4h.csv", CACHE_1H / "mnq_1h.parquet",
    ),
    "YM": _spec(
        "YM", 1.0, 5.0, 1.50, "futures",
        DERIVED_4H / "ym_4h.csv", CACHE_1H / "ym_1h.parquet",
    ),
}


ALL_SYMBOLS: List[str] = list(MARKETS.keys())


def _spread(tick: float, family: str) -> SpreadModel:
    # FX gets slightly wider ETH/open widen; metals/CFDs/futures share index-style.
    if family == "fx":
        return SpreadModel(
            rth_half_spread_ticks=0.5,
            eth_half_spread_ticks=1.0,
            open_widen_half_spread_ticks=1.0,
            low_volume_threshold=50.0,
            low_volume_multiplier=1.5,
            tick_size=tick,
        )
    return SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def ensure_4h_csv(market: MarketSpec) -> Path:
    """Return a readable 4h CSV; build from 1h parquet/csv when needed."""
    if market.csv.exists() and market.csv.stat().st_size > 0:
        return market.csv
    if market.source_1h is None or not market.source_1h.exists():
        raise FileNotFoundError(
            "Missing 4h CSV for %s (%s) and no 1h source" % (market.symbol, market.csv)
        )
    src = market.source_1h
    if src.suffix == ".parquet":
        raw = pd.read_parquet(src)
    else:
        raw = pd.read_csv(src)
    ts_col = "ts" if "ts" in raw.columns else "ts_event"
    ts = pd.to_datetime(raw[ts_col], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(raw[ts_col], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    raw = raw.assign(ts_event=ts).dropna(subset=["ts_event"]).set_index("ts_event").sort_index()
    ohlc = raw[["open", "high", "low", "close"]].astype(float)
    vol = raw["volume"].astype(float) if "volume" in raw.columns else pd.Series(0.0, index=raw.index)
    # Align to NY wall-clock 4h buckets (00/04/08/12/16/20).
    grouped = ohlc.resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    grouped["volume"] = vol.resample("4h", label="left", closed="left").sum()
    grouped = grouped.dropna(subset=["open", "high", "low", "close"])
    out = grouped.reset_index()
    out["symbol"] = market.symbol
    market.csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(market.csv, index=False)
    return market.csv


def load_4h(path: Path, symbol: str) -> pd.DataFrame:
    # Allow callers to pass MarketSpec.csv before ensure; rebuild if missing.
    if symbol.upper() in MARKETS:
        path = ensure_4h_csv(MARKETS[symbol.upper()])
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df["ts_event"], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    df = df.assign(ts_event=ts).dropna(subset=["ts_event"]).set_index("ts_event").sort_index()
    return df


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    force: bool,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> dict:
    strategy_id = "%s_quarterly_atr4_fade" % market.symbol.lower()
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = load_4h(market.csv, market.symbol)
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": market.tick,
        "entry_qty": 2,
        "tp1_qty": 1,
        "atr_len": 14,
        "atr_mult": 4.0,
        "risk_range_frac": 0.5,
        "max_trades_per_quarter": 2,
        "timeframe": "4h",
        "record_levels": False,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="quarterly_atr4_fade",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4h",
                    max_contracts=2,
                    max_open_orders=32,
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
    _progress(output_root, "  %s bars=%s" % (market.symbol, f"{len(df):,}"))
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
        "# Quarterly ±4×ATR first-touch fade (broker-like)",
        "",
        "Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14); first touch fades;",
        "2 contracts; 1@mid + runner@opposite ±4×ATR; reverse once on runner fill;",
        "max 2 trades/quarter; risk = 0.5× open-week range.",
        "",
        "| Market | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    csv_rows = []
    for m in rows:
        stress = float(m.get("intrabar_stress_dd_usd") or 0.0)
        ns = float(m.get("net_over_stress") or 0.0)
        lines.append(
            "| %s | %s | %d | %d | $%s | $%s | %.2f | %.1f%% | %.2f |"
            % (
                m["market"],
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
        "Promote gate: treat as research until causality audit + multi-year N/S hold.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(csv_rows).to_csv(output_root / "summary.csv", index=False)

    email = [
        "potions: quarterly ±4×ATR fade broker-like complete",
        "",
        "Hub: %s" % output_root.resolve(),
        "Book: open-week mid ±4×ATR first-touch fade; 2 lots; mid scaleout;",
        "runner @ opposite ±4×ATR → reverse; max 2 trades/quarter.",
        "",
    ]
    for m in rows:
        email.append(
            "  %s  net=$%s  N/S=%.2f  trades=%d  units=%d  WR=%.0f%%  PF=%.2f"
            % (
                m["market"],
                f"{float(m.get('net_usd') or 0.0):,.0f}",
                float(m.get("net_over_stress") or 0.0),
                int(m.get("trades") or 0),
                int(m.get("units") or 0),
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
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    rows: List[dict] = []
    try:
        for sym in symbols:
            market = MARKETS[sym.upper()]
            rows.append(run_one(output_root=output_root, market=market, force=force, start=start, end=end))
            write_summary(output_root, rows)
        write_summary(output_root, rows)
        write_run_manifest(
            output_root,
            data_inputs=[MARKETS[s.upper()].csv for s in symbols],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "plugin": "quarterly_atr4_fade",
                "entry_qty": 2,
                "atr_mult": 4.0,
                "risk_range_frac": 0.5,
                "max_trades_per_quarter": 2,
                "timeframe": "4h",
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
            "potions: quarterly ±4×ATR fade FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: quarterly ±4×ATR fade FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(subject="potions: quarterly ±4×ATR fade broker-like complete", body=body)
        _progress(output_root, "email sent")
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--symbol",
        action="append",
        default=None,
        help="Repeatable; default GBPUSD,US30,NAS100",
    )
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbol or ["GBPUSD", "US30", "NAS100"]
    for s in symbols:
        if s.upper() not in MARKETS:
            raise SystemExit("Unknown symbol %s (want %s)" % (s, ",".join(MARKETS)))
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    run_batch(
        output_root=args.output_root,
        symbols=symbols,
        force=args.force,
        email=args.email,
        start=start,
        end=end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
