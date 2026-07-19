"""EURUSD monthly hourly charts with PMC, OR, PDH/PDL, and ATR SuperTrend.

Layout::

    live/state/eurusd_monthly_hourly_charts/
      INDEX.md
      charts/
        2016/
          eurusd_hourly_2016_01.png … _12.png
          INDEX.md

Each chart (America/New_York):
- Hourly candles + alternating day shades
- Previous-month close (month-wide)
- Per-day **opening range** 09:30–09:45 (segments span that day only)
- Per-day **prior-day high/low** (segments span that day only)
- Markers when OR expands through PDH (▲) or PDL (▼)
- Hourly ATR SuperTrend trail (default 14 × 3.0)
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import default_eurusd_paths, ensure_eurusd_platform_files
from .ym_hourly_st_pmc_retest_replay import load_prev_month_close_map, resample_hourly


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
DAY_SHADE_A = "#e8eef5"
DAY_SHADE_B = "#f5efe6"
PMC_COLOR = "#e65100"
ST_BULL = "#00897b"
ST_BEAR = "#c62828"
OR_COLOR = "#1565c0"
PDH_COLOR = "#6a1b9a"
PDL_COLOR = "#6a1b9a"
OR_START = time(9, 30)
OR_END = time(9, 45)


def load_1m(one_m_path: Path, symbol: str = "EURUSD") -> pd.DataFrame:
    print("Loading FX 1m %s ..." % one_m_path, flush=True)
    df = pd.read_csv(one_m_path)
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY)
    df = df.set_index("ts_event").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    print("  1m bars: %s" % f"{len(df):,}", flush=True)
    return df[keep]


def build_daily_levels(one_m: pd.DataFrame) -> pd.DataFrame:
    """Per NY calendar day: OR 09:30–09:45 + full-day high/low."""
    if one_m.empty:
        return pd.DataFrame(columns=["or_high", "or_low", "day_high", "day_low"])
    rows = []
    for day, g in one_m.groupby(one_m.index.date):
        day_high = float(g["high"].max())
        day_low = float(g["low"].min())
        opening = g[(g.index.time >= OR_START) & (g.index.time < OR_END)]
        if opening.empty:
            or_high = np.nan
            or_low = np.nan
        else:
            or_high = float(opening["high"].max())
            or_low = float(opening["low"].min())
        rows.append(
            {
                "date": day,
                "or_high": or_high,
                "or_low": or_low,
                "day_high": day_high,
                "day_low": day_low,
            }
        )
    out = pd.DataFrame(rows).set_index("date").sort_index()
    print("  daily level rows: %s" % f"{len(out):,}", flush=True)
    return out


def month_windows(
    hourly: pd.DataFrame,
    start: Optional[date],
    end: Optional[date],
) -> List[Tuple[int, int, pd.Timestamp, pd.Timestamp]]:
    idx = hourly.index
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        idx = idx[idx < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if len(idx) == 0:
        return []
    keys = sorted({(int(ts.year), int(ts.month)) for ts in idx})
    out: List[Tuple[int, int, pd.Timestamp, pd.Timestamp]] = []
    for year, month in keys:
        t0 = pd.Timestamp(year=year, month=month, day=1, tz=NY)
        t1 = t0 + pd.offsets.MonthBegin(1)
        out.append((year, month, t0, t1))
    return out


def shade_days(ax, window_start: pd.Timestamp, window_end: pd.Timestamp) -> None:
    day = window_start.normalize()
    end = (window_end - pd.Timedelta(seconds=1)).normalize()
    i = 0
    while day <= end:
        nxt = day + pd.Timedelta(days=1)
        color = DAY_SHADE_A if (i % 2 == 0) else DAY_SHADE_B
        ax.axvspan(day, min(nxt, window_end), color=color, alpha=0.85, zorder=0)
        ax.axvline(day, color="#b0bec5", linewidth=0.4, linestyle=":", alpha=0.5, zorder=1)
        day = nxt
        i += 1


def plot_candles(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    width_days = (1.0 / 24.0) * 0.58
    x = mdates.date2num(df.index.to_pydatetime())
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    price_span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(price_span * 0.001, 1e-6)

    ax.vlines(x, lows, highs, color=colors, linewidth=0.55, alpha=0.9, zorder=3)
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
                alpha=0.85,
                zorder=4,
            )
        )


def draw_pmc(ax, window_start: pd.Timestamp, pmc: Optional[float]) -> Optional[float]:
    if pmc is None or not np.isfinite(pmc):
        return None
    ax.axhline(
        float(pmc),
        color=PMC_COLOR,
        linestyle="-.",
        linewidth=1.3,
        alpha=0.95,
        label="Prev month close",
        zorder=5,
    )
    ax.text(
        window_start,
        float(pmc),
        "  PMC %.5f" % float(pmc),
        color=PMC_COLOR,
        fontsize=8,
        va="bottom",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    return float(pmc)


def draw_supertrend(ax, df: pd.DataFrame) -> None:
    if df.empty or "supertrend" not in df.columns:
        return
    bull = df["supertrend"].where(df["supertrend_trend"] == 1)
    bear = df["supertrend"].where(df["supertrend_trend"] == -1)
    ax.plot(df.index, bull, color=ST_BULL, linewidth=1.4, alpha=0.95, label="Hourly ST trail (bull)", zorder=7)
    ax.plot(df.index, bear, color=ST_BEAR, linewidth=1.4, alpha=0.95, label="Hourly ST trail (bear)", zorder=7)


def _prior_trading_row(daily_levels: pd.DataFrame, day: date) -> Optional[pd.Series]:
    prior = daily_levels[daily_levels.index < day]
    if prior.empty:
        return None
    return prior.iloc[-1]


def draw_day_or_pdhl(
    ax,
    daily_levels: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    *,
    pmc: Optional[float],
) -> List[float]:
    """Draw per-day OR + PDH/PDL segments (day span only) and expand markers."""
    extras: List[float] = []
    labeled_or = False
    labeled_pdh = False
    labeled_pdl = False
    labeled_exp_up = False
    labeled_exp_dn = False

    day = window_start.normalize()
    end = (window_end - pd.Timedelta(seconds=1)).normalize()
    while day <= end:
        d = day.date()
        nxt = day + pd.Timedelta(days=1)
        left = max(day, window_start)
        right = min(nxt, window_end)
        if left >= right or d not in daily_levels.index:
            day = nxt
            continue
        row = daily_levels.loc[d]
        or_h = float(row["or_high"]) if pd.notna(row["or_high"]) else None
        or_l = float(row["or_low"]) if pd.notna(row["or_low"]) else None

        # Light OR band for this day only (matplotlib date units).
        if or_h is not None and or_l is not None and or_h >= or_l:
            x0 = mdates.date2num(left.to_pydatetime())
            x1 = mdates.date2num(right.to_pydatetime())
            ax.add_patch(
                plt.Rectangle(
                    (x0, or_l),
                    x1 - x0,
                    max(or_h - or_l, 1e-8),
                    facecolor="#90caf9",
                    edgecolor="none",
                    alpha=0.28,
                    zorder=1,
                    label="OR 09:30–09:45" if not labeled_or else None,
                )
            )
            ax.hlines(
                or_h,
                left,
                right,
                colors=OR_COLOR,
                linestyles="-",
                linewidth=1.05,
                alpha=0.9,
                zorder=5,
            )
            ax.hlines(
                or_l,
                left,
                right,
                colors=OR_COLOR,
                linestyles="-",
                linewidth=1.05,
                alpha=0.9,
                zorder=5,
            )
            extras.extend([or_h, or_l])
            labeled_or = True

        prior = _prior_trading_row(daily_levels, d)
        pdh = float(prior["day_high"]) if prior is not None else None
        pdl = float(prior["day_low"]) if prior is not None else None
        if pdh is not None:
            ax.hlines(
                pdh,
                left,
                right,
                colors=PDH_COLOR,
                linestyles="--",
                linewidth=0.95,
                alpha=0.85,
                zorder=5,
                label="Prior day high" if not labeled_pdh else None,
            )
            extras.append(pdh)
            labeled_pdh = True
        if pdl is not None:
            ax.hlines(
                pdl,
                left,
                right,
                colors=PDL_COLOR,
                linestyles=":",
                linewidth=0.95,
                alpha=0.85,
                zorder=5,
                label="Prior day low" if not labeled_pdl else None,
            )
            extras.append(pdl)
            labeled_pdl = True

        # Markers: OR expands through PDH / PDL. Mid-day x for readability.
        mid = left + (right - left) * 0.5
        if or_h is not None and pdh is not None and or_h >= pdh:
            ax.scatter(
                [mid],
                [or_h],
                marker="^",
                s=28,
                color="#0d47a1",
                zorder=8,
                label="OR expands thru PDH" if not labeled_exp_up else None,
            )
            labeled_exp_up = True
        if or_l is not None and pdl is not None and or_l <= pdl:
            ax.scatter(
                [mid],
                [or_l],
                marker="v",
                s=28,
                color="#4a148c",
                zorder=8,
                label="OR expands thru PDL" if not labeled_exp_dn else None,
            )
            labeled_exp_dn = True

        day = nxt
    return extras


def plot_month(
    out_path: Path,
    month_hourly: pd.DataFrame,
    daily_levels: pd.DataFrame,
    *,
    year: int,
    month: int,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    pmc: Optional[float],
    atr_len: int,
    atr_mult: float,
) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(20, 8.2))
    shade_days(ax, window_start, window_end)
    plot_candles(ax, month_hourly)
    pmc_val = draw_pmc(ax, window_start, pmc)
    level_vals = draw_day_or_pdhl(ax, daily_levels, window_start, window_end, pmc=pmc_val)
    draw_supertrend(ax, month_hourly)

    title = (
        "EURUSD %04d-%02d — hourly NY | OR + PDH/PDL | ATR ST %d×%g"
        % (year, month, atr_len, atr_mult)
    )
    if pmc_val is not None:
        title = "%s | PMC %.5f" % (title, pmc_val)
    else:
        title = "%s | PMC n/a" % title
    ax.set_title(title, fontsize=12)
    ax.set_ylabel("EURUSD")
    ax.set_xlabel("Time (America/New_York)")
    ax.set_xlim(window_start, window_end)

    if not month_hourly.empty:
        lo = float(month_hourly["low"].min())
        hi = float(month_hourly["high"].max())
        st = month_hourly["supertrend"].dropna()
        if not st.empty:
            lo = min(lo, float(st.min()))
            hi = max(hi, float(st.max()))
        if pmc_val is not None:
            lo = min(lo, pmc_val)
            hi = max(hi, pmc_val)
        if level_vals:
            lo = min(lo, min(level_vals))
            hi = max(hi, max(level_vals))
        pad = max((hi - lo) * 0.04, 1e-4)
        ax.set_ylim(lo - pad, hi + pad)

    ax.grid(True, color="#cfd8dc", linewidth=0.45, alpha=0.55, zorder=1)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d", tz=NY))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 6, 12, 18], tz=NY))
    for label in ax.get_xticklabels():
        label.set_rotation(70)
        label.set_fontsize(7)
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def write_indexes(
    output_root: Path,
    rows: List[Dict[str, object]],
    *,
    atr_len: int,
    atr_mult: float,
) -> None:
    by_year: Dict[int, List[Dict[str, object]]] = {}
    for row in rows:
        by_year.setdefault(int(row["year"]), []).append(row)

    root_lines = [
        "# EURUSD monthly hourly charts",
        "",
        "Hourly candles by **year / month** (America/New_York).",
        "",
        "- Alternating calendar-day background shades",
        "- Orange dash-dot = **previous month close** (month-wide)",
        "- Blue band / lines = **opening range 09:30–09:45** (that day only)",
        "- Purple dashed / dotted = **prior-day high / low** (that day only)",
        "- ▲ / ▼ = OR expands through PDH / PDL",
        "- Teal / red = **hourly ATR SuperTrend** trail (ATR %d × %g)" % (atr_len, atr_mult),
        "",
        "Related session pack (1m RTH only on OR-expand days): "
        "[`../eurusd_or_expand_session_charts/INDEX.md`](../eurusd_or_expand_session_charts/INDEX.md).",
        "",
        "## Years",
        "",
    ]
    for year in sorted(by_year):
        year_dir = output_root / "charts" / str(year)
        year_rows = sorted(by_year[year], key=lambda r: int(r["month"]))
        ylines = [
            "# EURUSD %d — monthly hourly charts" % year,
            "",
            "ATR SuperTrend trail: **%d × %g**. OR + PDH/PDL per day." % (atr_len, atr_mult),
            "",
            "| Month | Hourly bars | PMC | Chart |",
            "|---|---:|---:|---|",
        ]
        for row in year_rows:
            pmc = row["pmc"]
            pmc_s = "%.5f" % pmc if pmc is not None else "n/a"
            rel = Path(str(row["chart"])).name
            ylines.append(
                "| %04d-%02d | %d | %s | [%s](%s) |"
                % (int(row["year"]), int(row["month"]), int(row["bars"]), pmc_s, rel, rel)
            )
        (year_dir / "INDEX.md").write_text("\n".join(ylines) + "\n", encoding="utf-8")
        root_lines.append(
            "- [%d](charts/%d/INDEX.md) — %d months" % (year, year, len(year_rows))
        )

    root_lines.extend(
        [
            "",
            "## All months",
            "",
            "| # | Month | Hourly bars | PMC | Chart |",
            "|---:|---|---:|---:|---|",
        ]
    )
    for i, row in enumerate(rows, start=1):
        pmc = row["pmc"]
        pmc_s = "%.5f" % pmc if pmc is not None else "n/a"
        root_lines.append(
            "| %d | %04d-%02d | %d | %s | [%s](%s) |"
            % (
                i,
                int(row["year"]),
                int(row["month"]),
                int(row["bars"]),
                pmc_s,
                Path(str(row["chart"])).name,
                row["chart"],
            )
        )

    (output_root / "INDEX.md").write_text("\n".join(root_lines) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)


def build_charts(
    *,
    one_m_path: Path,
    daily_path: Path,
    output_root: Path,
    start: Optional[date],
    end: Optional[date],
    force: bool,
    atr_len: int,
    atr_mult: float,
) -> int:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)

    one_m = load_1m(one_m_path)
    daily_levels = build_daily_levels(one_m)
    hourly = resample_hourly(one_m)
    print("  hourly bars: %s" % f"{len(hourly):,}", flush=True)
    print("Computing hourly ATR SuperTrend (%d × %g) ..." % (atr_len, atr_mult), flush=True)
    hourly = compute_supertrend(hourly, atr_len=atr_len, multiplier=atr_mult)
    pmc_map = load_prev_month_close_map(daily_path)
    windows = month_windows(hourly, start, end)
    print("Monthly charts to build: %d" % len(windows), flush=True)

    rows: List[Dict[str, object]] = []
    for i, (year, month, t0, t1) in enumerate(windows, start=1):
        month_hourly = hourly[(hourly.index >= t0) & (hourly.index < t1)].copy()
        if month_hourly.empty:
            continue
        pmc = pmc_map.get((year, month))
        rel = "charts/%d/eurusd_hourly_%04d_%02d.png" % (year, year, month)
        out_path = output_root / rel
        if force or not out_path.exists():
            plot_month(
                out_path,
                month_hourly,
                daily_levels,
                year=year,
                month=month,
                window_start=t0,
                window_end=t1,
                pmc=pmc,
                atr_len=atr_len,
                atr_mult=atr_mult,
            )
        rows.append(
            {
                "year": year,
                "month": month,
                "bars": int(len(month_hourly)),
                "pmc": float(pmc) if pmc is not None else None,
                "chart": rel,
            }
        )
        if i % 12 == 0 or i == len(windows):
            print("  %d / %d months" % (i, len(windows)), flush=True)

    write_indexes(output_root, rows, atr_len=atr_len, atr_mult=atr_mult)
    print("Wrote %d charts → %s" % (len(rows), output_root), flush=True)
    return len(rows)


def _parse_ymd(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="EURUSD monthly hourly charts with OR, PDH/PDL, PMC, ATR ST."
    )
    parser.add_argument("--one-m", type=Path, default=None)
    parser.add_argument("--daily", type=Path, default=None)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_monthly_hourly_charts",
    )
    parser.add_argument("--start", type=_parse_ymd, default=None, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", type=_parse_ymd, default=None, help="YYYY-MM-DD inclusive")
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ensure-convert", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    raw, default_1m, default_daily = default_eurusd_paths(REPO)
    if args.ensure_convert or not default_1m.exists():
        if raw.exists():
            ensure_eurusd_platform_files(REPO, force=bool(args.ensure_convert))
    one_m = args.one_m or default_1m
    daily = args.daily or default_daily
    if not one_m.exists():
        raise SystemExit("Missing 1m CSV: %s" % one_m)
    if not daily.exists():
        raise SystemExit("Missing daily CSV: %s" % daily)

    build_charts(
        one_m_path=one_m,
        daily_path=daily,
        output_root=args.output_root,
        start=args.start,
        end=args.end,
        force=bool(args.force),
        atr_len=int(args.atr_len),
        atr_mult=float(args.atr_mult),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
