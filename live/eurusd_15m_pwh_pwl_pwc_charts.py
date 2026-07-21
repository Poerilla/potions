"""EURUSD 15m Mon–Fri charts: PWH/PWL/PWC + Monday OR (H/L/mid).

Random sample of weeks (default 150). Prior-week high/low/close are from the
previous Monday→Friday NY session. Monday OR = this week's Monday session
high/low; mid = (Mon high + Mon low) / 2. Off-scale levels use corner badges.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
DEFAULT_OUT = REPO / "live" / "state" / "eurusd_15m_pwh_pwl_pwc_charts"


def resample_15m(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("15min", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def monday_week_bounds(monday: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    monday = pd.Timestamp(monday)
    if monday.tzinfo is None:
        monday = NY_TZ.localize(monday.to_pydatetime())
    else:
        monday = monday.tz_convert(NY)
    monday0 = NY_TZ.localize(datetime.combine(monday.date(), time(0, 0)))
    while monday0.weekday() != 0:
        monday0 -= timedelta(days=1)
    friday_end = monday0 + timedelta(days=5)  # Sat 00:00 exclusive
    return pd.Timestamp(monday0), pd.Timestamp(friday_end)


def prior_week_levels(
    m15: pd.DataFrame, monday: pd.Timestamp
) -> Optional[Dict[str, float]]:
    """PWH/PWL/PWC from the previous Mon–Fri week."""
    this_mon, _ = monday_week_bounds(monday)
    prev_mon = this_mon - timedelta(days=7)
    prev_end = this_mon
    prev = m15[(m15.index >= prev_mon) & (m15.index < prev_end)]
    if prev.empty:
        return None
    return {
        "pwh": float(prev["high"].max()),
        "pwl": float(prev["low"].min()),
        "pwc": float(prev["close"].iloc[-1]),
    }


def monday_or_levels(
    m15: pd.DataFrame, monday: pd.Timestamp
) -> Optional[Dict[str, float]]:
    """This week's Monday NY session high / low / mid."""
    mon0, _ = monday_week_bounds(monday)
    tue0 = mon0 + timedelta(days=1)
    mon_bars = m15[(m15.index >= mon0) & (m15.index < tue0)]
    if mon_bars.empty:
        return None
    hi = float(mon_bars["high"].max())
    lo = float(mon_bars["low"].min())
    return {"or_high": hi, "or_low": lo, "or_mid": 0.5 * (hi + lo)}


def monday_candidates(m15: pd.DataFrame) -> List[pd.Timestamp]:
    idx = m15.index
    mondays: List[pd.Timestamp] = []
    seen = set()
    for ts in idx[::96]:
        ny = ts.tz_convert(NY)
        monday0 = pd.Timestamp(NY_TZ.localize(datetime.combine(ny.date(), time(0, 0))))
        while monday0.weekday() != 0:
            monday0 -= timedelta(days=1)
        key = int(monday0.value)
        if key in seen:
            continue
        seen.add(key)
        _, end = monday_week_bounds(monday0)
        if monday0 - timedelta(days=7) < idx[0]:
            continue
        if end > idx[-1] + timedelta(minutes=15):
            continue
        week = m15[(m15.index >= monday0) & (m15.index < end)]
        if len(week) < 48:
            continue
        mondays.append(monday0)
    return mondays


def pick_mondays(m15: pd.DataFrame, *, n: int, seed: int) -> List[pd.Timestamp]:
    cands = monday_candidates(m15)
    if len(cands) <= n:
        return list(cands)
    rng = random.Random(seed)
    return sorted(rng.sample(cands, n))


def _draw_level(
    ax,
    y: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    color: str,
    label: str,
    style: str = "--",
    lw: float = 1.4,
) -> None:
    ax.hlines(
        y,
        mdates.date2num(pd.Timestamp(start).to_pydatetime()),
        mdates.date2num(pd.Timestamp(end).to_pydatetime()),
        colors=color,
        linestyles=style,
        linewidth=lw,
        alpha=0.95,
        zorder=5,
        label=label,
    )


def plot_week(
    m15: pd.DataFrame,
    monday: pd.Timestamp,
    out_path: Path,
    *,
    chart_idx: int,
) -> dict:
    start, end = monday_week_bounds(monday)
    plot = m15[(m15.index >= start) & (m15.index < end)].copy()
    if len(plot) < 48:
        return {}

    levels = prior_week_levels(m15, start)
    or_lv = monday_or_levels(m15, start)
    win_lo = float(plot["low"].min())
    win_hi = float(plot["high"].max())
    # Include OR in window so Mon range is visible when possible
    if or_lv:
        win_lo = min(win_lo, or_lv["or_low"])
        win_hi = max(win_hi, or_lv["or_high"])
    price_span = max(win_hi - win_lo, 1e-5)

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (15.0 / (24.0 * 60.0)) * 0.75
    axis_tz = plot.index.tz

    fig, ax = plt.subplots(figsize=(20, 7.5))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.45, alpha=0.85, zorder=3)
    min_body = max(price_span * 0.0008, 1e-6)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.25,
                alpha=0.8,
                zorder=4,
            )
        )

    # Monday OR band + mid (Tue→Fri emphasis; draw across full week for context)
    level_status: Dict[str, str] = {}
    if or_lv:
        mon0 = start
        tue0 = start + timedelta(days=1)
        # Shade Monday session lightly
        ax.axvspan(
            mdates.date2num(mon0.to_pydatetime()),
            mdates.date2num(tue0.to_pydatetime()),
            color="#90caf9",
            alpha=0.12,
            zorder=0,
            label="Monday",
        )
        ax.axhspan(
            or_lv["or_low"],
            or_lv["or_high"],
            color="#90caf9",
            alpha=0.10,
            zorder=1,
        )
        or_specs = [
            ("or_high", or_lv["or_high"], "#1565c0", "Mon high", "--"),
            ("or_low", or_lv["or_low"], "#ef6c00", "Mon low", "--"),
            ("or_mid", or_lv["or_mid"], "#00838f", "Mon mid", ":"),
        ]
        for key, val, color, name, style in or_specs:
            _draw_level(
                ax,
                val,
                start,
                end - timedelta(minutes=15),
                color=color,
                label="%s %.5f" % (name, val),
                style=style,
                lw=1.5 if key != "or_mid" else 1.3,
            )
            level_status[key] = "on"

    if levels:
        specs = [
            ("pwh", levels["pwh"], "#6a1b9a", "PWH"),
            ("pwl", levels["pwl"], "#bf360c", "PWL"),
            ("pwc", levels["pwc"], "#4527a0", "PWC"),
        ]
        for key, val, color, name in specs:
            if win_lo <= val <= win_hi:
                _draw_level(
                    ax,
                    val,
                    start,
                    end - timedelta(minutes=15),
                    color=color,
                    label="%s %.5f" % (name, val),
                    style="-.",
                    lw=1.2,
                )
                level_status[key] = "on"
            elif val > win_hi:
                level_status[key] = "above"
            else:
                level_status[key] = "below"

        above_bits = ["%s %.5f" % (k.upper(), levels[k]) for k, s in level_status.items() if s == "above" and k in levels]
        below_bits = ["%s %.5f" % (k.upper(), levels[k]) for k, s in level_status.items() if s == "below" and k in levels]
        if above_bits:
            ax.annotate(
                "▲ " + ", ".join(above_bits),
                xy=(0.99, 0.98),
                xycoords="axes fraction",
                ha="right",
                va="top",
                fontsize=8,
                color="#333333",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#888", alpha=0.92),
                zorder=10,
            )
        if below_bits:
            ax.annotate(
                "▼ " + ", ".join(below_bits),
                xy=(0.99, 0.02),
                xycoords="axes fraction",
                ha="right",
                va="bottom",
                fontsize=8,
                color="#333333",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#888", alpha=0.92),
                zorder=10,
            )

    pad = max(price_span * 0.06, 1e-5)
    ax.set_ylim(win_lo - pad, win_hi + pad)

    mon_s = start.strftime("%Y-%m-%d")
    fri_s = (end - timedelta(days=1)).strftime("%Y-%m-%d")
    or_txt = ""
    if or_lv:
        or_txt = " | Mon OR %.5f–%.5f mid %.5f" % (
            or_lv["or_high"],
            or_lv["or_low"],
            or_lv["or_mid"],
        )
    ax.set_title(
        "EURUSD 15m — #%03d | Mon %s → Fri %s | PWH/PWL/PWC + Monday OR%s"
        % (chart_idx, mon_s, fri_s, or_txt),
        fontsize=10,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.5, alpha=0.7)
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=axis_tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d", tz=axis_tz))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 6, 12, 18], tz=axis_tz))
    ax.set_xlabel("Time (America/New_York) — Monday to Friday")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return {
        "idx": chart_idx,
        "monday": mon_s,
        "friday": fri_s,
        "bars": len(plot),
        "pwh": levels["pwh"] if levels else None,
        "pwl": levels["pwl"] if levels else None,
        "pwc": levels["pwc"] if levels else None,
        "or_high": or_lv["or_high"] if or_lv else None,
        "or_low": or_lv["or_low"] if or_lv else None,
        "or_mid": or_lv["or_mid"] if or_lv else None,
        "pwh_status": level_status.get("pwh", "n/a"),
        "pwl_status": level_status.get("pwl", "n/a"),
        "pwc_status": level_status.get("pwc", "n/a"),
        "path": out_path.name,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args(list(argv) if argv is not None else None)

    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD 1m → 15m...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    m15 = resample_15m(concat_all_1m(bars_by_day))
    if m15.index.tz is None:
        m15.index = m15.index.tz_localize(NY)
    else:
        m15.index = m15.index.tz_convert(NY)
    print("  %s 15m bars" % f"{len(m15):,}", flush=True)

    weeks = pick_mondays(m15, n=args.n, seed=args.seed)
    print("  sampled %d Mon–Fri weeks (seed %d)" % (len(weeks), args.seed), flush=True)

    charts_dir = args.output_root / "charts"
    if charts_dir.exists():
        for p in charts_dir.glob("*.png"):
            p.unlink()
    charts_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, monday in enumerate(weeks, start=1):
        out = charts_dir / ("%03d_%s.png" % (i, monday.strftime("%Y-%m-%d")))
        meta = plot_week(m15, monday, out, chart_idx=i)
        if meta:
            rows.append(meta)
        if i % 25 == 0:
            print("  wrote %d/%d" % (i, len(weeks)), flush=True)

    lines = [
        "# EURUSD 15m — PWH / PWL / PWC + Monday OR",
        "",
        "**%d** random Mon→Fri weeks (seed `%d`). No trades." % (len(rows), args.seed),
        "",
        "- 15-minute candles (no SuperTrend)",
        "- **Monday OR:** Mon high / Mon low / **mid** = (H+L)/2",
        "- **PWH / PWL / PWC** = prior Mon–Fri week high / low / close",
        "- Off-scale prior-week levels hidden (corner ▲/▼ badges)",
        "",
        "| # | Mon | Fri | Mon high | Mon mid | Mon low | Chart |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for r in rows:
        def f5(key: str) -> str:
            v = r.get(key)
            return "n/a" if v is None else "%.5f" % v

        lines.append(
            "| %d | %s | %s | %s | %s | %s | [charts/%s](charts/%s) |"
            % (
                r["idx"],
                r["monday"],
                r["friday"],
                f5("or_high"),
                f5("or_mid"),
                f5("or_low"),
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d charts → %s" % (len(rows), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
