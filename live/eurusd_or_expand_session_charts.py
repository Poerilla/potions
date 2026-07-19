"""EURUSD RTH 1m session charts for OR-through-PDH/PDL days.

Related to ``eurusd_monthly_hourly_charts``: only sessions where the NY
opening range (09:30–09:45) already expands through the prior trading day's
high and/or low.

Each chart is one NY RTH session (09:30–16:00) of 1-minute candles with:
- Opening-range band + high/low
- Prior-day high / low (session-wide guides)
- Marker at the **first 1m bar** that trades through PDH and/or PDL

Layout::

    live/state/eurusd_or_expand_session_charts/
      INDEX.md
      charts/<year>/
        eurusd_1m_<YYYY-MM-DD>_or_thru_pdh.png
        ...
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .fx_data import default_eurusd_paths, ensure_eurusd_platform_files
from .eurusd_monthly_hourly_charts import OR_END, OR_START, build_daily_levels, load_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
RTH_END = time(16, 0)
OR_COLOR = "#1565c0"
PDH_COLOR = "#6a1b9a"
PDL_COLOR = "#6a1b9a"
TOUCH_PDH = "#0d47a1"
TOUCH_PDL = "#4a148c"


def _session_slice(one_m: pd.DataFrame, session: date) -> pd.DataFrame:
    start = pd.Timestamp(datetime.combine(session, OR_START), tz=NY)
    end = pd.Timestamp(datetime.combine(session, RTH_END), tz=NY)
    return one_m[(one_m.index >= start) & (one_m.index < end)].copy()


def _opening_range(rth: pd.DataFrame) -> Optional[Tuple[float, float]]:
    opening = rth[(rth.index.time >= OR_START) & (rth.index.time < OR_END)]
    if opening.empty:
        return None
    return float(opening["high"].max()), float(opening["low"].min())


def _first_touch(
    rth: pd.DataFrame,
    *,
    level: float,
    side: str,
) -> Optional[pd.Timestamp]:
    """First 1m bar that trades through ``level`` (``pdh`` high>=, ``pdl`` low<=)."""
    if rth.empty:
        return None
    if side == "pdh":
        hits = rth[rth["high"] >= float(level)]
    else:
        hits = rth[rth["low"] <= float(level)]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


def expand_sessions(daily_levels: pd.DataFrame) -> pd.DataFrame:
    """Rows where OR expands through prior trading-day high and/or low."""
    rows = []
    dates = list(daily_levels.index)
    for i, d in enumerate(dates):
        if i == 0:
            continue
        row = daily_levels.loc[d]
        prior = daily_levels.loc[dates[i - 1]]
        if pd.isna(row["or_high"]) or pd.isna(row["or_low"]):
            continue
        pdh = float(prior["day_high"])
        pdl = float(prior["day_low"])
        or_h = float(row["or_high"])
        or_l = float(row["or_low"])
        thru_pdh = or_h >= pdh
        thru_pdl = or_l <= pdl
        if not (thru_pdh or thru_pdl):
            continue
        rows.append(
            {
                "session": d,
                "or_high": or_h,
                "or_low": or_l,
                "pdh": pdh,
                "pdl": pdl,
                "thru_pdh": bool(thru_pdh),
                "thru_pdl": bool(thru_pdl),
                "prior_session": dates[i - 1],
            }
        )
    return pd.DataFrame(rows)


def plot_candles_1m(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    width_days = (1.0 / (24.0 * 60.0)) * 0.7
    x = mdates.date2num(df.index.to_pydatetime())
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    price_span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(price_span * 0.0015, 1e-6)
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
                linewidth=0.2,
                alpha=0.85,
                zorder=4,
            )
        )


def plot_session(
    out_path: Path,
    rth: pd.DataFrame,
    *,
    session: date,
    or_high: float,
    or_low: float,
    pdh: float,
    pdl: float,
    thru_pdh: bool,
    thru_pdl: bool,
) -> Dict[str, object]:
    session_start = pd.Timestamp(datetime.combine(session, OR_START), tz=NY)
    session_end = pd.Timestamp(datetime.combine(session, RTH_END), tz=NY)
    or_end_ts = pd.Timestamp(datetime.combine(session, OR_END), tz=NY)

    touch_pdh_ts = _first_touch(rth, level=pdh, side="pdh") if thru_pdh else None
    touch_pdl_ts = _first_touch(rth, level=pdl, side="pdl") if thru_pdl else None

    fig, ax = plt.subplots(1, 1, figsize=(18, 8.0))
    # Soft OR-window shade on the time axis.
    ax.axvspan(session_start, or_end_ts, color="#bbdefb", alpha=0.18, zorder=0, label="OR window 09:30–09:45")
    plot_candles_1m(ax, rth)

    # OR price band across the full RTH session (levels stay relevant all day).
    ax.axhspan(or_low, or_high, color="#90caf9", alpha=0.22, zorder=1, label="Opening range")
    ax.axhline(or_high, color=OR_COLOR, linewidth=1.15, alpha=0.95, label="OR high %.5f" % or_high)
    ax.axhline(or_low, color=OR_COLOR, linewidth=1.15, alpha=0.95, label="OR low %.5f" % or_low)

    ax.axhline(pdh, color=PDH_COLOR, linestyle="--", linewidth=1.25, alpha=0.95, label="PDH %.5f" % pdh)
    ax.axhline(pdl, color=PDL_COLOR, linestyle=":", linewidth=1.25, alpha=0.95, label="PDL %.5f" % pdl)

    if touch_pdh_ts is not None:
        ax.axvline(touch_pdh_ts, color=TOUCH_PDH, linestyle="-", linewidth=1.0, alpha=0.75, zorder=6)
        ax.scatter(
            [touch_pdh_ts],
            [pdh],
            marker="^",
            s=90,
            color=TOUCH_PDH,
            zorder=8,
            label="Thru PDH @ %s" % touch_pdh_ts.strftime("%H:%M"),
        )
        ax.annotate(
            "thru PDH\n%s" % touch_pdh_ts.strftime("%H:%M"),
            xy=(touch_pdh_ts, pdh),
            xytext=(8, 12),
            textcoords="offset points",
            fontsize=8,
            color=TOUCH_PDH,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.5},
        )
    if touch_pdl_ts is not None:
        ax.axvline(touch_pdl_ts, color=TOUCH_PDL, linestyle="-", linewidth=1.0, alpha=0.75, zorder=6)
        ax.scatter(
            [touch_pdl_ts],
            [pdl],
            marker="v",
            s=90,
            color=TOUCH_PDL,
            zorder=8,
            label="Thru PDL @ %s" % touch_pdl_ts.strftime("%H:%M"),
        )
        ax.annotate(
            "thru PDL\n%s" % touch_pdl_ts.strftime("%H:%M"),
            xy=(touch_pdl_ts, pdl),
            xytext=(8, -22),
            textcoords="offset points",
            fontsize=8,
            color=TOUCH_PDL,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.5},
        )

    flags = []
    if thru_pdh:
        flags.append("PDH")
    if thru_pdl:
        flags.append("PDL")
    ax.set_title(
        "EURUSD %s — RTH 1m | OR expands thru %s"
        % (session.isoformat(), "+".join(flags)),
        fontsize=12,
    )
    ax.set_ylabel("EURUSD")
    ax.set_xlabel("Time (America/New_York)")
    ax.set_xlim(session_start, session_end)
    lo = min(float(rth["low"].min()), or_low, pdl)
    hi = max(float(rth["high"].max()), or_high, pdh)
    pad = max((hi - lo) * 0.05, 1e-4)
    ax.set_ylim(lo - pad, hi + pad)
    ax.grid(True, color="#cfd8dc", linewidth=0.45, alpha=0.55, zorder=1)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=NY))
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=range(0, 60, 15), tz=NY))
    for label in ax.get_xticklabels():
        label.set_rotation(0)
        label.set_fontsize(8)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)

    return {
        "touch_pdh_ts": touch_pdh_ts.isoformat() if touch_pdh_ts is not None else "",
        "touch_pdl_ts": touch_pdl_ts.isoformat() if touch_pdl_ts is not None else "",
    }


def write_indexes(output_root: Path, rows: List[Dict[str, object]]) -> None:
    by_year: Dict[int, List[Dict[str, object]]] = {}
    for row in rows:
        by_year.setdefault(int(str(row["session"])[:4]), []).append(row)

    root = [
        "# EURUSD OR-expand RTH session charts",
        "",
        "Related to [`../eurusd_monthly_hourly_charts/INDEX.md`](../eurusd_monthly_hourly_charts/INDEX.md).",
        "",
        "Only NY sessions where the **opening range (09:30–09:45)** expands through the "
        "**prior trading day's high and/or low**. Each chart is **1m RTH 09:30–16:00** with OR, "
        "PDH/PDL, and a marker at the first 1m bar that trades through the level.",
        "",
        "## Years",
        "",
    ]
    for year in sorted(by_year):
        year_rows = by_year[year]
        year_dir = output_root / "charts" / str(year)
        ylines = [
            "# EURUSD OR-expand sessions — %d" % year,
            "",
            "| Session | Thru | Touch PDH | Touch PDL | Chart |",
            "|---|---|---|---|---|",
        ]
        for row in year_rows:
            flags = []
            if row["thru_pdh"]:
                flags.append("PDH")
            if row["thru_pdl"]:
                flags.append("PDL")
            name = Path(str(row["chart"])).name
            ylines.append(
                "| %s | %s | %s | %s | [%s](%s) |"
                % (
                    row["session"],
                    "+".join(flags),
                    str(row.get("touch_pdh_hm") or ""),
                    str(row.get("touch_pdl_hm") or ""),
                    name,
                    name,
                )
            )
        (year_dir / "INDEX.md").write_text("\n".join(ylines) + "\n", encoding="utf-8")
        root.append("- [%d](charts/%d/INDEX.md) — %d sessions" % (year, year, len(year_rows)))

    root.extend(
        [
            "",
            "## All sessions",
            "",
            "| # | Session | Thru | Touch PDH | Touch PDL | Chart |",
            "|---:|---|---|---|---|---|",
        ]
    )
    for i, row in enumerate(rows, start=1):
        flags = []
        if row["thru_pdh"]:
            flags.append("PDH")
        if row["thru_pdl"]:
            flags.append("PDL")
        root.append(
            "| %d | %s | %s | %s | %s | [%s](%s) |"
            % (
                i,
                row["session"],
                "+".join(flags),
                str(row.get("touch_pdh_hm") or ""),
                str(row.get("touch_pdl_hm") or ""),
                Path(str(row["chart"])).name,
                row["chart"],
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(root) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)


def build_charts(
    *,
    one_m_path: Path,
    output_root: Path,
    start: Optional[date],
    end: Optional[date],
    force: bool,
    max_charts: Optional[int],
) -> int:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)

    one_m = load_1m(one_m_path)
    daily_levels = build_daily_levels(one_m)
    expands = expand_sessions(daily_levels)
    if start is not None:
        expands = expands[expands["session"] >= start]
    if end is not None:
        expands = expands[expands["session"] <= end]
    expands = expands.reset_index(drop=True)
    if max_charts is not None:
        expands = expands.iloc[: int(max_charts)].copy()
    print("OR-expand sessions to chart: %d" % len(expands), flush=True)

    rows: List[Dict[str, object]] = []
    for i, row in enumerate(expands.itertuples(index=False), start=1):
        session: date = row.session
        rth = _session_slice(one_m, session)
        if rth.empty:
            continue
        flags = []
        if row.thru_pdh:
            flags.append("pdh")
        if row.thru_pdl:
            flags.append("pdl")
        fname = "eurusd_1m_%s_or_thru_%s.png" % (session.isoformat(), "_".join(flags))
        rel = "charts/%d/%s" % (session.year, fname)
        out_path = output_root / rel
        meta = {}
        if force or not out_path.exists():
            meta = plot_session(
                out_path,
                rth,
                session=session,
                or_high=float(row.or_high),
                or_low=float(row.or_low),
                pdh=float(row.pdh),
                pdl=float(row.pdl),
                thru_pdh=bool(row.thru_pdh),
                thru_pdl=bool(row.thru_pdl),
            )
        else:
            # Still compute touch times for the index when skipping plot.
            touch_pdh = _first_touch(rth, level=float(row.pdh), side="pdh") if row.thru_pdh else None
            touch_pdl = _first_touch(rth, level=float(row.pdl), side="pdl") if row.thru_pdl else None
            meta = {
                "touch_pdh_ts": touch_pdh.isoformat() if touch_pdh is not None else "",
                "touch_pdl_ts": touch_pdl.isoformat() if touch_pdl is not None else "",
            }

        def _hm(iso: str) -> str:
            if not iso:
                return ""
            return pd.Timestamp(iso).tz_convert(NY).strftime("%H:%M")

        rows.append(
            {
                "session": session.isoformat(),
                "thru_pdh": bool(row.thru_pdh),
                "thru_pdl": bool(row.thru_pdl),
                "or_high": float(row.or_high),
                "or_low": float(row.or_low),
                "pdh": float(row.pdh),
                "pdl": float(row.pdl),
                "touch_pdh_ts": meta.get("touch_pdh_ts", ""),
                "touch_pdl_ts": meta.get("touch_pdl_ts", ""),
                "touch_pdh_hm": _hm(str(meta.get("touch_pdh_ts") or "")),
                "touch_pdl_hm": _hm(str(meta.get("touch_pdl_ts") or "")),
                "chart": rel,
            }
        )
        if i % 50 == 0 or i == len(expands):
            print("  %d / %d" % (i, len(expands)), flush=True)

    write_indexes(output_root, rows)
    print("Wrote %d charts → %s" % (len(rows), output_root), flush=True)
    return len(rows)


def _parse_ymd(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="EURUSD 1m RTH charts for OR-through-PDH/PDL sessions."
    )
    parser.add_argument("--one-m", type=Path, default=None)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_or_expand_session_charts",
    )
    parser.add_argument("--start", type=_parse_ymd, default=None)
    parser.add_argument("--end", type=_parse_ymd, default=None)
    parser.add_argument("--max-charts", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ensure-convert", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    raw, default_1m, _daily = default_eurusd_paths(REPO)
    if args.ensure_convert or not default_1m.exists():
        if raw.exists():
            ensure_eurusd_platform_files(REPO, force=bool(args.ensure_convert))
    one_m = args.one_m or default_1m
    if not one_m.exists():
        raise SystemExit("Missing 1m CSV: %s" % one_m)

    build_charts(
        one_m_path=one_m,
        output_root=args.output_root,
        start=args.start,
        end=args.end,
        force=bool(args.force),
        max_charts=args.max_charts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
