"""Shared helpers for trend_momentum TF study and multi-market sweep."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .store import FlatFileStore
from .strategies.trend_momentum import default_config
from .v2b_strategy_cross_market_replay import MARKETS as CME_MARKETS
from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
FEE = 1.50
SLIPPAGE = 1.0
JPY_USD = 110.0

# Index CFDs / FX ticks (extend broker defaults)
TICKS: Dict[str, float] = {
    **{k: float(v) for k, v in DEFAULT_TICK_SIZE.items()},
    "US30": 0.1,
    "NAS100": 0.1,
}

RTH_INSTRUMENTS = {"US30", "NAS100", "NQ", "YM", "MNQ", "MYM", "ES", "MES"}


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    kind: str  # fx | metal | index_cfd | cme
    source: str  # fx_csv | cme


STUDY_INSTRUMENTS: List[InstrumentSpec] = [
    InstrumentSpec("USDJPY", "fx", "fx_csv"),
    InstrumentSpec("XAUUSD", "metal", "fx_csv"),
    InstrumentSpec("US30", "index_cfd", "fx_csv"),
    InstrumentSpec("NQ", "cme", "cme"),
]

SWEEP_INSTRUMENTS: List[InstrumentSpec] = [
    InstrumentSpec("EURUSD", "fx", "fx_csv"),
    InstrumentSpec("GBPUSD", "fx", "fx_csv"),
    InstrumentSpec("USDJPY", "fx", "fx_csv"),
    InstrumentSpec("AUDJPY", "fx", "fx_csv"),
    InstrumentSpec("XAUUSD", "metal", "fx_csv"),
    InstrumentSpec("XAGUSD", "metal", "fx_csv"),
    InstrumentSpec("US30", "index_cfd", "fx_csv"),
    InstrumentSpec("NAS100", "index_cfd", "fx_csv"),
    InstrumentSpec("NQ", "cme", "cme"),
    InstrumentSpec("YM", "cme", "cme"),
    InstrumentSpec("MNQ", "cme", "cme"),
    InstrumentSpec("MYM", "cme", "cme"),
]

TIMEFRAMES_STUDY = ["5m", "15m", "1h", "4h", "D"]


def resample_n_min(df_1m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df_1m.copy()
    rule = "%dmin" % minutes
    return (
        df_1m.resample(rule, label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def resample_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("4h", label="left", closed="left", origin="start_day")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def resample_daily(df_1m: pd.DataFrame) -> pd.DataFrame:
    # NY calendar day from index
    idx = df_1m.index
    if getattr(idx, "tz", None) is not None:
        day = idx.tz_convert("America/New_York").date
    else:
        day = pd.DatetimeIndex(idx).tz_localize("America/New_York").date
    g = df_1m.copy()
    g["_day"] = day
    out = g.groupby("_day", sort=True).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    # timestamp = day open 00:00 NY as naive/localized
    ts = pd.to_datetime(out.index.astype(str)).tz_localize("America/New_York")
    out.index = ts
    return out


def load_1m_frame(spec: InstrumentSpec) -> pd.DataFrame:
    sym = spec.symbol
    if spec.source == "fx_csv":
        path = REPO / "fx" / ("%s_1m.csv" % sym.lower())
        if not path.exists():
            raise FileNotFoundError(path)
        by_day = load_fx_1m_by_ny_date(path, sym)
        return concat_all_1m(by_day)
    key = sym.lower()
    if key not in CME_MARKETS:
        raise KeyError("No CME market config for %s" % sym)
    mcfg = CME_MARKETS[key]
    by_day = load_1m_by_ny_date_any(mcfg.dbn_path, key)
    frames = []
    for d, df in sorted(by_day.items()):
        if mcfg.start and d < mcfg.start:
            continue
        frames.append(df)
    if not frames:
        raise RuntimeError("No 1m bars for %s" % sym)
    return pd.concat(frames).sort_index()


def _filter_rth_1m(df1: pd.DataFrame) -> pd.DataFrame:
    if df1.empty:
        return df1
    df = df1.copy()
    if getattr(df.index, "tz", None) is None:
        df.index = pd.DatetimeIndex(df.index).tz_localize(
            "America/New_York", ambiguous="infer", nonexistent="shift_forward"
        )
    else:
        df.index = df.index.tz_convert("America/New_York")
    parts = []
    for d, part in df.groupby(df.index.date):
        rb = rth_bars(part, d, dense=False)
        if rb is not None and len(rb):
            parts.append(rb)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def frame_to_bars(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    start: Optional[date] = None,
) -> List[Bar]:
    out: List[Bar] = []
    for ts, row in df.iterrows():
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            d = t.tz_convert("America/New_York").date()
            ts_str = t.isoformat()
        else:
            d = t.date()
            ts_str = t.isoformat()
        if start is not None and d < start:
            continue
        out.append(
            Bar(
                instrument=symbol,
                timeframe=timeframe,
                ts=ts_str,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source="trend_momentum",
            )
        )
    return out


def default_start_for_tf(timeframe: str) -> Optional[date]:
    """5m/15m use 2018+ so studies finish in reasonable time."""
    if timeframe in {"5m", "15m"}:
        return date(2018, 1, 1)
    return None


def load_signal_bars(
    spec: InstrumentSpec,
    timeframe: str,
    df1_cache: Optional[pd.DataFrame] = None,
) -> List[Bar]:
    sym = spec.symbol
    df1 = df1_cache if df1_cache is not None else load_1m_frame(spec)
    rth_only = sym in RTH_INSTRUMENTS and timeframe not in {"D", "4h"}
    work = df1
    if rth_only:
        work = _filter_rth_1m(df1)
        if work.empty:
            raise RuntimeError("No RTH bars for %s" % sym)

    if timeframe == "5m":
        df = resample_n_min(work, 5)
    elif timeframe == "15m":
        df = resample_n_min(work, 15)
    elif timeframe == "1h":
        df = resample_hourly(work)
    elif timeframe == "4h":
        base = _filter_rth_1m(df1) if sym in RTH_INSTRUMENTS else df1
        df = resample_4h(base)
    elif timeframe == "D":
        daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
        if spec.source == "fx_csv" and daily_path.exists():
            raw = pd.read_csv(daily_path)
            ts_col = "ts" if "ts" in raw.columns else ("date" if "date" in raw.columns else raw.columns[0])
            raw[ts_col] = pd.to_datetime(raw[ts_col])
            raw = raw.set_index(ts_col).sort_index()
            df = raw.rename(columns={c: c.lower() for c in raw.columns})
            for need in ("open", "high", "low", "close"):
                if need not in df.columns:
                    raise ValueError("daily csv missing %s for %s" % (need, sym))
            if "volume" not in df.columns:
                df["volume"] = 0.0
        elif spec.source == "cme":
            daily_path = CME_MARKETS[sym.lower()].daily_path
            if not Path(daily_path).exists():
                alt = REPO / ("%s/%s_daily.csv" % (sym.lower(), sym.lower()))
                daily_path = alt
            raw = pd.read_csv(daily_path)
            ts_col = "ts" if "ts" in raw.columns else ("date" if "date" in raw.columns else raw.columns[0])
            raw[ts_col] = pd.to_datetime(raw[ts_col])
            raw = raw.set_index(ts_col).sort_index()
            df = raw.rename(columns={c: c.lower() for c in raw.columns})
            if "volume" not in df.columns:
                df["volume"] = 0.0
        else:
            df = resample_daily(df1)
    else:
        raise ValueError("Unsupported timeframe %s" % timeframe)

    return frame_to_bars(df, sym, timeframe, start=default_start_for_tf(timeframe))


def plugin_config_for(symbol: str, timeframe: str) -> dict:
    tick = float(TICKS.get(symbol, 0.25))
    rth_only = symbol in RTH_INSTRUMENTS and timeframe not in {"D"}
    return default_config(
        tick,
        signal_tf=timeframe,
        rth_only=rth_only,
        entry_qty=1,
        max_contracts=1,
        trend_end_mode="opposite",
    )


def net_usd_approx(symbol: str, net_usd: float) -> float:
    if symbol in {"USDJPY", "AUDJPY"}:
        return float(net_usd) / JPY_USD
    return float(net_usd)


def run_cell(
    *,
    out_root: Path,
    spec: InstrumentSpec,
    timeframe: str,
    force: bool = False,
    df1_cache: Optional[pd.DataFrame] = None,
) -> dict:
    sym = spec.symbol
    slug = "%s_%s" % (sym.lower(), timeframe.lower())
    state_root = out_root / "states" / slug
    metrics_path = state_root / "metrics.json"
    if metrics_path.exists() and not force:
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    print("[%s %s] loading bars..." % (sym, timeframe), flush=True)
    bars = load_signal_bars(spec, timeframe, df1_cache=df1_cache)
    print("[%s %s] %s bars" % (sym, timeframe, f"{len(bars):,}"), flush=True)
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    tick = float(TICKS.get(sym, 0.25))
    DEFAULT_TICK_SIZE[sym] = tick
    cfg = plugin_config_for(sym, timeframe)
    instance = StrategyInstance(
        strategy_id=slug,
        strategy_type="trend_momentum",
        version="v1",
        instrument=sym,
        broker_instrument=sym,
        account_mode="paper",
        enabled=True,
        timeframes=timeframe,
        max_contracts=1,
        config_json=json.dumps(cfg, sort_keys=True),
    )
    store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
    Engine(store=store, slippage_ticks=SLIPPAGE, tick_size={sym: tick}).replay_bars(bars)
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, candidate=slug)
    audit_root = out_root / "audits" / slug
    # Persist bars for audit equity path
    bars_dir = state_root / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)
    bar_csv = bars_dir / ("%s_%s.csv" % (sym, timeframe))
    with bar_csv.open("w", encoding="utf-8") as fh:
        fh.write("ts,open,high,low,close,volume\n")
        for b in bars:
            fh.write(
                "%s,%.10f,%.10f,%.10f,%.10f,%.4f\n"
                % (b.ts, b.open, b.high, b.low, b.close, b.volume)
            )

    audit_bars = read_bars(bar_csv, ts_field="ts")
    result = audit_units(
        name="%s trend_momentum %s" % (sym, timeframe),
        slug=slug,
        source=fills_path,
        bar_source=bar_csv,
        bars=audit_bars,
        units=units,
        instrument=sym,
        notes="trend_momentum StrategyPlugin; fee $1.50; 1-tick slip",
        output_root=audit_root / slug,
        fee_per_unit=FEE,
    )
    net_u = net_usd_approx(sym, float(result.net_usd))
    stress_u = net_usd_approx(sym, float(result.intrabar_mtm_dd_usd))
    ns = (net_u / abs(stress_u)) if stress_u else 0.0
    wr = (100.0 * result.win_units / result.units) if result.units else 0.0
    row = {
        "symbol": sym,
        "kind": spec.kind,
        "timeframe": timeframe,
        "slug": slug,
        "units": result.units,
        "trades": result.trades,
        "net_usd_approx": net_u,
        "stress_usd_approx": stress_u,
        "closed_dd_usd_approx": net_usd_approx(sym, float(result.close_mtm_dd_usd)),
        "net_stress": ns,
        "win_rate_pct": wr,
        "state_root": str(state_root),
    }
    metrics_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        "[%s %s] net≈$%.0f stress≈$%.0f N/S=%.2f units=%d"
        % (sym, timeframe, net_u, stress_u, ns, result.units),
        flush=True,
    )
    return row


def write_summary(out_root: Path, rows: Sequence[dict], title: str) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    import csv

    path = out_root / "summary.csv"
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    ranked = sorted(rows, key=lambda r: float(r.get("net_stress") or 0), reverse=True)
    lines = ["# %s" % title, "", "| Rank | Symbol | TF | Net≈$ | Stress≈$ | N/S | Units | WR% |", "|---:|---|---|---:|---:|---:|---:|---:|"]
    for i, r in enumerate(ranked, 1):
        lines.append(
            "| %d | %s | %s | %.0f | %.0f | %.2f | %s | %.1f |"
            % (
                i,
                r["symbol"],
                r["timeframe"],
                float(r["net_usd_approx"]),
                float(r["stress_usd_approx"]),
                float(r["net_stress"]),
                r["units"],
                float(r["win_rate_pct"]),
            )
        )
    (out_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
