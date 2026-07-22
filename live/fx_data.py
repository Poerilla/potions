"""Load and convert Histdata-style FX 1m files for the live StrategyPlugin path.

Source layout (e.g. ``fx/raw/EURUSD.txt``)::

    <TICKER>,<DTYYYYMMDD>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>
    EURUSD,20030506,000000,1.12921,1.1293,1.1291,1.12921,592300001

Timestamps are treated as naive America/New_York (EST/EDT with DST).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

NY = "America/New_York"

PLATFORM_1M_COLUMNS = ["ts_event", "open", "high", "low", "close", "volume", "symbol"]
DAILY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "symbol"]


def _read_histdata_frame(src: Path, symbol: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_csv(
        src,
        header=None,
        names=["ticker", "ymd", "hms", "open", "high", "low", "close", "volume"],
        dtype={
            "ticker": "string",
            "ymd": "string",
            "hms": "string",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        },
        skiprows=1,
    )
    # Drop malformed / header-echo rows.
    df = df[df["ymd"].str.fullmatch(r"\d{8}", na=False)].copy()
    df["hms"] = df["hms"].str.zfill(6)
    naive = pd.to_datetime(df["ymd"] + df["hms"], format="%Y%m%d%H%M%S")
    # Prefer DST fold=0 on ambiguous clocks; shift nonexistent spring-forward holes.
    try:
        ts = naive.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
    except Exception:
        ts = naive.dt.tz_localize(NY, ambiguous=True, nonexistent="shift_forward")
    out = pd.DataFrame(
        {
            "ts_event": ts,
            "open": df["open"].to_numpy(),
            "high": df["high"].to_numpy(),
            "low": df["low"].to_numpy(),
            "close": df["close"].to_numpy(),
            "volume": df["volume"].fillna(0.0).to_numpy(),
            "symbol": (symbol or str(df["ticker"].iloc[0])).upper(),
        }
    )
    return out.sort_values("ts_event").reset_index(drop=True)


def convert_histdata_to_platform(
    src: Path,
    out_1m: Path,
    out_daily: Path,
    *,
    symbol: Optional[str] = None,
) -> Dict[str, object]:
    """Convert Histdata 1m → platform 1m CSV + NY-calendar daily CSV."""
    out_1m.parent.mkdir(parents=True, exist_ok=True)
    out_daily.parent.mkdir(parents=True, exist_ok=True)

    print("Reading Histdata %s ..." % src, flush=True)
    one_m = _read_histdata_frame(src, symbol=symbol)
    print("  %s 1m rows" % f"{len(one_m):,}", flush=True)
    # Persist as UTC ISO so pandas 3.8 ``parse_dates`` stays datetimelike.
    export = one_m.copy()
    export["ts_event"] = export["ts_event"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    export.to_csv(out_1m, index=False, columns=PLATFORM_1M_COLUMNS)

    g = one_m.copy()
    g["date"] = g["ts_event"].dt.tz_convert(NY).dt.date
    daily = (
        g.groupby("date", sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    daily["symbol"] = str(one_m["symbol"].iloc[0]).upper()
    daily.to_csv(out_daily, index=False, columns=DAILY_COLUMNS)

    return {
        "rows": int(len(one_m)),
        "days": int(len(daily)),
        "symbol": str(one_m["symbol"].iloc[0]).upper(),
        "first_ts": one_m["ts_event"].iloc[0].isoformat(),
        "last_ts": one_m["ts_event"].iloc[-1].isoformat(),
        "out_1m": str(out_1m),
        "out_daily": str(out_daily),
    }


def load_fx_1m_by_ny_date(path: Path, symbol: str = "EURUSD") -> Dict[date, pd.DataFrame]:
    """Load a platform FX 1m CSV into ``{ny_date: ohlcv frame}``."""
    print("Loading FX CSV %s (%s) ..." % (path, symbol.upper()), flush=True)
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    if df.empty:
        return {}
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY)
    df = df.set_index("ts_event").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume", "symbol") if c in df.columns]
    df = df[keep]
    gby = {d: g.copy() for d, g in df.groupby(df.index.date)}
    print("  %s NY dates with bars" % f"{len(gby):,}", flush=True)
    return gby


def default_eurusd_paths(repo: Path) -> Tuple[Path, Path, Path]:
    raw = repo / "fx" / "raw" / "EURUSD.txt"
    one_m = repo / "fx" / "eurusd_1m.csv"
    daily = repo / "fx" / "eurusd_daily.csv"
    return raw, one_m, daily


def ensure_eurusd_platform_files(repo: Path, *, force: bool = False) -> Tuple[Path, Path]:
    raw, one_m, daily = default_eurusd_paths(repo)
    if not raw.exists():
        raise FileNotFoundError(raw)
    if force or not one_m.exists() or not daily.exists():
        info = convert_histdata_to_platform(raw, one_m, daily, symbol="EURUSD")
        print(
            "Converted EURUSD: %s rows, %s days (%s → %s)"
            % (f"{info['rows']:,}", f"{info['days']:,}", info["first_ts"], info["last_ts"]),
            flush=True,
        )
    return one_m, daily


def _read_mt5_1m_frame(
    src: Path,
    *,
    symbol: str,
    source_tz: str = "Europe/Athens",
) -> pd.DataFrame:
    """Read MT5-exported 1m TSV (DateTime Open High Low Close Volume TickVolume).

    Timestamps are naive broker-server clocks. For NAS100 dumps validated against
    Databento NQ, ``Europe/Athens`` (EET/EEST) aligns cash-open dumps with NY RTH.
    """
    df = pd.read_csv(
        src,
        sep="\t",
        dtype={
            "DateTime": "string",
            "Open": "float64",
            "High": "float64",
            "Low": "float64",
            "Close": "float64",
            "Volume": "float64",
            "TickVolume": "float64",
        },
    )
    need = {"DateTime", "Open", "High", "Low", "Close"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError("%s missing columns: %s" % (src, sorted(missing)))
    naive = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    try:
        ts = naive.dt.tz_localize(source_tz, ambiguous="infer", nonexistent="shift_forward")
    except Exception:
        ts = naive.dt.tz_localize(source_tz, ambiguous=True, nonexistent="shift_forward")
    vol = df["Volume"].fillna(0.0) if "Volume" in df.columns else 0.0
    out = pd.DataFrame(
        {
            "ts_event": ts,
            "open": df["Open"].to_numpy(),
            "high": df["High"].to_numpy(),
            "low": df["Low"].to_numpy(),
            "close": df["Close"].to_numpy(),
            "volume": vol.to_numpy() if hasattr(vol, "to_numpy") else vol,
            "symbol": symbol.upper(),
        }
    )
    out = out.dropna(subset=["ts_event", "open", "high", "low", "close"])
    return out.sort_values("ts_event").drop_duplicates(subset=["ts_event"]).reset_index(drop=True)


def convert_mt5_1m_to_platform(
    src: Path,
    out_1m: Path,
    out_daily: Path,
    *,
    symbol: str,
    source_tz: str = "Europe/Athens",
) -> Dict[str, object]:
    """Convert MT5 1m TSV → platform 1m CSV + NY-calendar daily CSV."""
    out_1m.parent.mkdir(parents=True, exist_ok=True)
    out_daily.parent.mkdir(parents=True, exist_ok=True)

    print("Reading MT5 %s (tz=%s) ..." % (src, source_tz), flush=True)
    one_m = _read_mt5_1m_frame(src, symbol=symbol, source_tz=source_tz)
    print("  %s 1m rows" % f"{len(one_m):,}", flush=True)

    export = one_m.copy()
    export["ts_event"] = export["ts_event"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    export.to_csv(out_1m, index=False, columns=PLATFORM_1M_COLUMNS)

    g = one_m.copy()
    g["date"] = g["ts_event"].dt.tz_convert(NY).dt.date
    daily = (
        g.groupby("date", sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    daily["symbol"] = symbol.upper()
    daily.to_csv(out_daily, index=False, columns=DAILY_COLUMNS)

    return {
        "rows": int(len(one_m)),
        "days": int(len(daily)),
        "symbol": symbol.upper(),
        "source_tz": source_tz,
        "first_ts": one_m["ts_event"].iloc[0].isoformat(),
        "last_ts": one_m["ts_event"].iloc[-1].isoformat(),
        "out_1m": str(out_1m),
        "out_daily": str(out_daily),
    }


def default_nas100_paths(repo: Path) -> Tuple[Path, Path, Path]:
    raw = repo / "fx" / "raw" / "NAS100_1m_data.csv"
    one_m = repo / "fx" / "nas100_1m.csv"
    daily = repo / "fx" / "nas100_daily.csv"
    return raw, one_m, daily


def ensure_nas100_platform_files(repo: Path, *, force: bool = False) -> Tuple[Path, Path]:
    raw, one_m, daily = default_nas100_paths(repo)
    if not raw.exists():
        raise FileNotFoundError(raw)
    if force or not one_m.exists() or not daily.exists():
        info = convert_mt5_1m_to_platform(raw, one_m, daily, symbol="NAS100", source_tz="Europe/Athens")
        print(
            "Converted NAS100: %s rows, %s days (%s → %s)"
            % (f"{info['rows']:,}", f"{info['days']:,}", info["first_ts"], info["last_ts"]),
            flush=True,
        )
    return one_m, daily


if __name__ == "__main__":
    import argparse
    import json

    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Convert Histdata/MT5 FX 1m to platform CSV + daily.")
    parser.add_argument("--src", type=Path, default=repo / "fx" / "raw" / "EURUSD.txt")
    parser.add_argument("--out-1m", type=Path, default=repo / "fx" / "eurusd_1m.csv")
    parser.add_argument("--out-daily", type=Path, default=repo / "fx" / "eurusd_daily.csv")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument(
        "--format",
        choices=("histdata", "mt5"),
        default="histdata",
        help="Raw file layout (mt5 = DateTime TSV like NAS100_1m_data.csv).",
    )
    parser.add_argument("--source-tz", default="Europe/Athens", help="Naive clock TZ for --format mt5.")
    args = parser.parse_args()
    if args.format == "mt5":
        meta = convert_mt5_1m_to_platform(
            args.src, args.out_1m, args.out_daily, symbol=args.symbol, source_tz=args.source_tz
        )
    else:
        meta = convert_histdata_to_platform(args.src, args.out_1m, args.out_daily, symbol=args.symbol)
    print(json.dumps(meta, indent=2))
