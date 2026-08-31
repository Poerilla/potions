"""FX / index quarterly 4h charts with week shades, opening-week range, ±4 ATR, month closes.

Layout::

    live/state/<symbol>_quarterly_4h_charts/
      INDEX.md
      EMAIL.txt
      charts/
        YYYY/
          <symbol>_4h_YYYY_Qn.png
          INDEX.md

Each chart covers one calendar quarter (3 months), starting from the first
January quarter in the 4h history:

- 4h candles (America/New_York)
- Alternating shade on each ISO week change
- Opening week of the quarter: high/low range band across the full chart
- Fixed horizontal levels at mid ±1..4× ATR(14) of the opening week
  (ATR = Wilder/EWM on 4h bars, taken at the last bar of the opening week)
- Closing price of each month in the quarter (horizontal guide + label)

Defaults remain GBPUSD; pass ``--symbol NAS100`` / ``US30`` (and ``--csv``) for indexes.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
DEFAULT_SYMBOL = "GBPUSD"
DEFAULT_OUT = REPO / "live" / "state" / "gbpusd_quarterly_4h_charts"
DEFAULT_CSV = REPO / "fx" / "gbpusd_4h.csv"

# Index CFDs use fewer decimals than FX pairs in labels.
INDEX_SYMBOLS = {"NAS100", "US30", "US500", "DE40", "UK100", "JP225"}


def price_fmt(symbol: str) -> str:
    return "%.2f" if symbol.upper() in INDEX_SYMBOLS else "%.5f"


def slug(symbol: str) -> str:
    return symbol.strip().lower()


def default_csv_for(symbol: str) -> Path:
    return REPO / "fx" / ("%s_4h.csv" % slug(symbol))


def default_out_for(symbol: str) -> Path:
    return REPO / "live" / "state" / ("%s_quarterly_4h_charts" % slug(symbol))

WEEK_SHADE_A = "#e8eef5"
WEEK_SHADE_B = "#f5efe6"
OPEN_WEEK_FILL = "#90caf9"
OPEN_WEEK_EDGE = "#1565c0"
ATR_COLORS = {
    1: "#546e7a",
    2: "#00838f",
    3: "#ef6c00",
    4: "#c62828",
}
MONTH_CLOSE_COLOR = "#e65100"
ATR_LEN = 14


def load_4h(path: Path, symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    print("Loading %s ..." % path, flush=True)
    df = pd.read_csv(path)
    if "symbol" in df.columns:
        syms = df["symbol"].astype(str).str.upper()
        root = symbol.upper()
        exact = syms == root
        if bool(exact.any()):
            df = df.loc[exact].copy()
        else:
            # Front-month rows use contract codes (YMM0, NQH1, …).
            df = df.loc[syms.str.startswith(root) & ~syms.str.contains("-", na=False)].copy()
    ts_col = "ts_event" if "ts_event" in df.columns else ("time" if "time" in df.columns else "ts")
    if ts_col not in df.columns:
        raise KeyError("4h csv needs ts_event/time/ts: %s" % path)
    # Tolerate already-localized strings (e.g. nas100_1h style) and UTC Z.
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    df = df.assign(ts_event=ts).dropna(subset=["ts_event"])
    df = df.set_index("ts_event").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep]
    print("  4h bars: %s" % f"{len(out):,}", flush=True)
    return out


def resample_1h_to_4h(path_1h: Path, symbol: str, out_csv: Path) -> Path:
    """Build a 4h CSV from an hourly file (NAS100 has 1h but no checked-in 4h)."""
    print("Resampling 1h → 4h: %s → %s" % (path_1h, out_csv), flush=True)
    df = pd.read_csv(path_1h)
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
    ohlc = (
        df.resample("4h", label="left", closed="left", origin="start_day")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum") if "volume" in df.columns else ("open", "count"),
        )
        .dropna(subset=["open"])
    )
    if "volume" not in df.columns:
        ohlc = ohlc.drop(columns=["volume"], errors="ignore")
        ohlc["volume"] = 0.0
    out = ohlc.reset_index()
    out["ts_event"] = out["ts_event"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["symbol"] = symbol.upper()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    print("  wrote %s bars" % f"{len(out):,}", flush=True)
    return out_csv


def wilder_atr(df: pd.DataFrame, atr_len: int = ATR_LEN) -> pd.Series:
    """Wilder ATR via EWM(alpha=1/len), matching SuperTrend ATR in this repo."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / float(atr_len), adjust=False, min_periods=atr_len).mean()
    atr.name = "atr"
    return atr


def quarter_windows(
    bars: pd.DataFrame,
    start: Optional[date],
    end: Optional[date],
    *,
    jan_only: bool = False,
) -> List[Tuple[int, int, pd.Timestamp, pd.Timestamp]]:
    idx = bars.index
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        idx = idx[idx < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if len(idx) == 0:
        return []
    keys = sorted({(int(ts.year), int((ts.month - 1) // 3 + 1)) for ts in idx})
    out: List[Tuple[int, int, pd.Timestamp, pd.Timestamp]] = []
    for year, quarter in keys:
        if jan_only and quarter != 1:
            continue
        month0 = 1 + (quarter - 1) * 3
        t0 = pd.Timestamp(year=year, month=month0, day=1, tz=NY)
        t1 = t0 + pd.offsets.MonthBegin(3)
        # Require some bars inside the quarter.
        if bars[(bars.index >= t0) & (bars.index < t1)].empty:
            continue
        out.append((year, quarter, t0, t1))
    return out


def week_bounds(ts: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Monday 00:00 NY → next Monday for the ISO week containing ts."""
    local = ts.tz_convert(NY) if ts.tzinfo is not None else ts.tz_localize(NY)
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def opening_week_slice(bars: pd.DataFrame, q_start: pd.Timestamp) -> pd.DataFrame:
    w0, w1 = week_bounds(q_start)
    # Opening week of the quarter: ISO week containing quarter start, clipped to
    # bars that fall inside the quarter (week may start before Jan 1).
    left = max(w0, q_start)
    return bars[(bars.index >= left) & (bars.index < w1)].copy()


def shade_weeks(ax, window_start: pd.Timestamp, window_end: pd.Timestamp) -> None:
    week0, _ = week_bounds(window_start)
    week = week0
    i = 0
    while week < window_end:
        nxt = week + pd.Timedelta(days=7)
        left = max(week, window_start)
        right = min(nxt, window_end)
        if left < right:
            color = WEEK_SHADE_A if (i % 2 == 0) else WEEK_SHADE_B
            ax.axvspan(left, right, color=color, alpha=0.85, zorder=0)
            ax.axvline(left, color="#b0bec5", linewidth=0.45, linestyle=":", alpha=0.55, zorder=1)
        week = nxt
        i += 1


def plot_candles(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    width_days = (4.0 / 24.0) * 0.62
    x = mdates.date2num(df.index.to_pydatetime())
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    price_span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(price_span * 0.001, 1e-6)

    ax.vlines(x, lows, highs, color=colors, linewidth=0.7, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, opens, closes, colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.25,
                alpha=0.88,
                zorder=4,
            )
        )


def draw_opening_week_range(
    ax,
    ow: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if ow.empty:
        return None, None, None
    hi = float(ow["high"].max())
    lo = float(ow["low"].min())
    mid = 0.5 * (hi + lo)
    ax.axhspan(
        lo,
        hi,
        color=OPEN_WEEK_FILL,
        alpha=0.22,
        zorder=1,
        label="Opening week H/L",
    )
    ax.hlines(hi, window_start, window_end, colors=OPEN_WEEK_EDGE, linestyles="-", linewidth=1.15, zorder=5)
    ax.hlines(lo, window_start, window_end, colors=OPEN_WEEK_EDGE, linestyles="-", linewidth=1.15, zorder=5)
    ax.text(
        window_start,
        hi,
        ("  Q open-week high " + fmt) % hi,
        color=OPEN_WEEK_EDGE,
        fontsize=8,
        va="bottom",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    ax.text(
        window_start,
        lo,
        ("  Q open-week low " + fmt) % lo,
        color=OPEN_WEEK_EDGE,
        fontsize=8,
        va="top",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    return hi, lo, mid


def draw_atr_bands(
    ax,
    mid: float,
    atr: float,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> List[float]:
    levels: List[float] = []
    for k in range(1, 5):
        color = ATR_COLORS[k]
        up = mid + k * atr
        dn = mid - k * atr
        ax.hlines(
            up,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=1.0 if k < 4 else 1.25,
            alpha=0.9,
            zorder=5,
            label="+/- %d×ATR(14)" % k if k == 1 else None,
        )
        ax.hlines(
            dn,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=1.0 if k < 4 else 1.25,
            alpha=0.9,
            zorder=5,
        )
        ax.text(
            window_end,
            up,
            (" +%d× " % k) + (fmt % up) + " ",
            color=color,
            fontsize=7.5,
            va="center",
            ha="left",
            zorder=6,
        )
        ax.text(
            window_end,
            dn,
            (" -%d× " % k) + (fmt % dn) + " ",
            color=color,
            fontsize=7.5,
            va="top",
            ha="left",
            zorder=6,
        )
        levels.extend([up, dn])
    # Mid reference
    ax.hlines(
        mid,
        window_start,
        window_end,
        colors="#37474f",
        linestyles=":",
        linewidth=1.0,
        alpha=0.85,
        zorder=5,
        label="Open-week mid",
    )
    levels.append(mid)
    return levels


def draw_month_closes(
    ax,
    bars: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> List[float]:
    """Last 4h close of each calendar month that intersects the quarter window."""
    if bars.empty:
        return []
    levels: List[float] = []
    labeled = False
    # Group by calendar month within window.
    months = sorted({(int(ts.year), int(ts.month)) for ts in bars.index})
    for year, month in months:
        m0 = pd.Timestamp(year=year, month=month, day=1, tz=NY)
        m1 = m0 + pd.offsets.MonthBegin(1)
        left = max(m0, window_start)
        right = min(m1, window_end)
        chunk = bars[(bars.index >= left) & (bars.index < right)]
        if chunk.empty:
            continue
        close = float(chunk["close"].iloc[-1])
        close_ts = chunk.index[-1]
        ax.hlines(
            close,
            left,
            right,
            colors=MONTH_CLOSE_COLOR,
            linestyles="-.",
            linewidth=1.35,
            alpha=0.95,
            zorder=6,
            label="Month close" if not labeled else None,
        )
        ax.scatter(
            [close_ts],
            [close],
            marker="o",
            s=28,
            color=MONTH_CLOSE_COLOR,
            zorder=8,
        )
        ax.text(
            close_ts,
            close,
            ("  %s close " % close_ts.strftime("%b")) + (fmt % close),
            color=MONTH_CLOSE_COLOR,
            fontsize=8,
            va="bottom",
            ha="left",
            zorder=7,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
        )
        levels.append(close)
        labeled = True
    return levels


def plot_quarter(
    *,
    bars: pd.DataFrame,
    atr_series: pd.Series,
    year: int,
    quarter: int,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
    symbol: str,
) -> Dict[str, object]:
    fmt = price_fmt(symbol)
    window = bars[(bars.index >= t0) & (bars.index < t1)].copy()
    ow = opening_week_slice(bars, t0)
    atr_val = None
    if not ow.empty and ow.index[-1] in atr_series.index:
        atr_val = float(atr_series.loc[ow.index[-1]])
        if not np.isfinite(atr_val):
            atr_val = None
    if atr_val is None and not ow.empty:
        # Fallback: last finite ATR at or before opening-week end.
        prior = atr_series.loc[: ow.index[-1]].dropna()
        if not prior.empty:
            atr_val = float(prior.iloc[-1])

    fig, ax = plt.subplots(figsize=(18, 8.5))
    shade_weeks(ax, t0, t1)
    plot_candles(ax, window)
    hi, lo, mid = draw_opening_week_range(ax, ow, t0, t1, fmt=fmt)
    extras: List[float] = []
    if mid is not None and atr_val is not None and atr_val > 0:
        extras.extend(draw_atr_bands(ax, mid, atr_val, t0, t1, fmt=fmt))
    extras.extend(draw_month_closes(ax, window, t0, t1, fmt=fmt))
    if hi is not None:
        extras.extend([hi, lo])

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is None or not np.isfinite(v):
                continue
            y_lo = min(y_lo, float(v))
            y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.04, 1e-4)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(t0, t1)
    atr_txt = (("ATR(14)=" + fmt) % atr_val) if atr_val is not None else "ATR n/a"
    ax.set_title(
        "%s 4h · %d Q%d (%s → %s) · week shades · open-week range · ±1..4×ATR · month closes · %s"
        % (
            symbol.upper(),
            year,
            quarter,
            t0.date().isoformat(),
            (t1 - pd.Timedelta(days=1)).date().isoformat(),
            atr_txt,
        )
    )
    ax.set_ylabel(symbol.upper())
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    return {
        "year": year,
        "quarter": quarter,
        "start": t0.date().isoformat(),
        "end": (t1 - pd.Timedelta(days=1)).date().isoformat(),
        "bars": int(len(window)),
        "open_week_high": hi,
        "open_week_low": lo,
        "open_week_mid": mid,
        "atr14": atr_val,
        "chart": str(out_path.relative_to(out_path.parents[2]) if False else out_path.name),
    }


def build(
    *,
    csv_path: Path,
    output_root: Path,
    start: Optional[date],
    end: Optional[date],
    jan_quarters_only: bool,
    force: bool,
    symbol: str = DEFAULT_SYMBOL,
) -> List[Dict[str, object]]:
    symbol = symbol.upper()
    sym_slug = slug(symbol)
    fmt = price_fmt(symbol)
    bars = load_4h(csv_path, symbol=symbol)
    atr_series = wilder_atr(bars, ATR_LEN)
    # Default start: first January 1 on or after first bar year if user said "Starting Jan".
    if start is None:
        first = bars.index[0]
        start = date(int(first.year) + (0 if first.month == 1 else 1), 1, 1)
        if first.month == 1 and first.day == 1:
            start = date(int(first.year), 1, 1)
        elif first.month > 1:
            start = date(int(first.year) + 1, 1, 1)
        else:
            start = date(int(first.year), 1, 1)

    windows = quarter_windows(bars, start, end, jan_only=jan_quarters_only)
    # Always include all quarters from Jan start year unless jan_only.
    if not jan_quarters_only:
        # Ensure we begin at a January quarter when possible.
        windows = [w for w in windows if not (w[0] == start.year and w[1] < 1)]
        # Drop quarters before the first Jan of start year.
        windows = [w for w in windows if (w[0], w[1]) >= (start.year, 1)]

    if force and output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    charts_root = output_root / "charts"
    charts_root.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, object]] = []
    for year, quarter, t0, t1 in windows:
        rel = Path("charts") / str(year) / ("%s_4h_%d_Q%d.png" % (sym_slug, year, quarter))
        out_path = output_root / rel
        if out_path.exists() and not force:
            rows.append(
                {
                    "year": year,
                    "quarter": quarter,
                    "start": t0.date().isoformat(),
                    "end": (t1 - pd.Timedelta(days=1)).date().isoformat(),
                    "chart": str(rel),
                    "cached": True,
                }
            )
            continue
        print("  chart %d Q%d ..." % (year, quarter), flush=True)
        meta = plot_quarter(
            bars=bars,
            atr_series=atr_series,
            year=year,
            quarter=quarter,
            t0=t0,
            t1=t1,
            out_path=out_path,
            symbol=symbol,
        )
        meta["chart"] = str(rel)
        rows.append(meta)

    _write_indexes(
        output_root,
        rows,
        start=start,
        end=end,
        jan_only=jan_quarters_only,
        symbol=symbol,
        csv_path=csv_path,
        fmt=fmt,
    )
    return rows


def _write_indexes(
    output_root: Path,
    rows: Sequence[Dict[str, object]],
    *,
    start: Optional[date],
    end: Optional[date],
    jan_only: bool,
    symbol: str,
    csv_path: Path,
    fmt: str,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    symbol = symbol.upper()

    by_year: Dict[int, List[Dict[str, object]]] = {}
    for r in rows:
        by_year.setdefault(int(r["year"]), []).append(r)

    for year, items in sorted(by_year.items()):
        lines = [
            "# %s 4h — %d" % (symbol, year),
            "",
            "| Q | Start | End | Bars | Open-week H/L | ATR(14) | Chart |",
            "|---:|---|---|---:|---|---:|---|",
        ]
        for r in sorted(items, key=lambda x: int(x["quarter"])):
            ow = ""
            if r.get("open_week_high") is not None:
                ow = (fmt + " / " + fmt) % (float(r["open_week_high"]), float(r["open_week_low"]))
            atr = "" if r.get("atr14") is None else (fmt % float(r["atr14"]))
            lines.append(
                "| Q%d | %s | %s | %s | %s | %s | [%s](%s) |"
                % (
                    int(r["quarter"]),
                    r.get("start", ""),
                    r.get("end", ""),
                    r.get("bars", ""),
                    ow,
                    atr,
                    Path(str(r["chart"])).name,
                    Path(str(r["chart"])).name,
                )
            )
        year_dir = output_root / "charts" / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        (year_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    scope = "Q1 only (Jan–Mar)" if jan_only else "all quarters (3-month windows)"
    try:
        csv_rel = csv_path.resolve().relative_to(REPO)
    except Exception:
        csv_rel = csv_path
    lines = [
        "# %s quarterly 4h charts" % symbol,
        "",
        "Generated from `%s` (America/New_York)." % csv_rel,
        "",
        "- Window: **3 months** per chart (%s)" % scope,
        "- Start: **%s**" % (start.isoformat() if start else "history"),
        "- End: **%s**" % (end.isoformat() if end else "history"),
        "- Alternating **ISO week** shading",
        "- **Opening week of the quarter** high/low as a range across the chart",
        "- Fixed bands at open-week mid **±1..4 × ATR(14)** (Wilder/EWM on 4h)",
        "- **Month closes** (last 4h close of Jan/Feb/Mar …) as orange guides",
        "",
        "Charts: **%d**" % len(rows),
        "",
        "| Year | Quarters | Index |",
        "|---:|---:|---|",
    ]
    for year in sorted(by_year):
        lines.append(
            "| %d | %d | [INDEX](charts/%d/INDEX.md) |"
            % (year, len(by_year[year]), year)
        )
    lines.append("")
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "potions: %s quarterly 4h charts complete" % symbol,
        "",
        "Hub: %s" % output_root,
        "Charts: %d (%s)" % (len(rows), scope),
        "Start: %s" % (start.isoformat() if start else "history"),
        "",
        "Each chart: 4h candles, alternating week shades, opening-week H/L range,",
        "±1..4×ATR(14) from open-week mid, and each month's closing price.",
        "",
        "See INDEX.md for per-year links.",
    ]
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", default=DEFAULT_SYMBOL, help="e.g. GBPUSD, NAS100, US30")
    ap.add_argument("--csv", type=Path, default=None, help="4h CSV (default: fx/<symbol>_4h.csv)")
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (default: first January in history)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD inclusive cutoff")
    ap.add_argument(
        "--jan-only",
        action="store_true",
        help="Only chart Q1 (Jan–Mar) each year",
    )
    ap.add_argument(
        "--build-4h-from-1h",
        type=Path,
        default=None,
        help="If set, resample this 1h CSV to fx/<symbol>_4h.csv before charting",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)

    symbol = str(args.symbol).upper()
    csv_path = args.csv or default_csv_for(symbol)
    output_root = args.output_root or default_out_for(symbol)

    if args.build_4h_from_1h is not None:
        csv_path = resample_1h_to_4h(Path(args.build_4h_from_1h), symbol, csv_path)

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    # User asked "Starting Jan" — default to all quarters from first Jan, not Q1-only.
    rows = build(
        csv_path=csv_path,
        output_root=output_root,
        start=start,
        end=end,
        jan_quarters_only=args.jan_only,
        force=args.force,
        symbol=symbol,
    )
    print("Wrote %d charts -> %s" % (len(rows), output_root), flush=True)
    if args.email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(subject="potions: %s quarterly 4h charts complete" % symbol, body=body)
        print("email sent", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
