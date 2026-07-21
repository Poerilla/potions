"""EURUSD hourly context charts: candles + ST ATR×3 + broken-trail dashes + PMC.

No trade markers. Each chart is a **Monday→Friday** NY week. Broken SuperTrend
levels are extended ~6 hours as dashed lines after a flip. Prior-month close is
drawn only when it falls inside the candle high/low range; if hidden, the title
and index say whether PMC sits **above** or **below** the week.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import (
    concat_all_1m,
    load_prev_month_close_map,
    resample_hourly,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
ATR_LEN = 14
ATR_MULT = 3.0
DEFAULT_OUT = REPO / "live" / "state" / "eurusd_st_pmc_context_charts"


def _broken_trail_segments(
    plot: pd.DataFrame,
    *,
    extend_hours: int,
) -> List[Tuple[pd.Timestamp, pd.Timestamp, float, str]]:
    """Return (start, end, price, side) for trails broken inside/near the window.

    Uses full history columns on ``plot`` (must include the pre-window bar when
    possible so a flip on the first hour is detected). ``side`` is the trail
    that broke: ``bull`` or ``bear``.
    """
    if len(plot) < 2 or "supertrend_trend" not in plot.columns:
        return []
    trend = plot["supertrend_trend"].astype(float)
    st = plot["supertrend"].astype(float)
    idx = plot.index
    segs: List[Tuple[pd.Timestamp, pd.Timestamp, float, str]] = []
    for i in range(1, len(plot)):
        if pd.isna(trend.iloc[i]) or pd.isna(trend.iloc[i - 1]):
            continue
        if int(trend.iloc[i]) == int(trend.iloc[i - 1]):
            continue
        if pd.isna(st.iloc[i - 1]):
            continue
        broken_side = "bull" if int(trend.iloc[i - 1]) == 1 else "bear"
        start = idx[i]
        end = start + timedelta(hours=extend_hours)
        segs.append((start, end, float(st.iloc[i - 1]), broken_side))
    return segs


def plot_window(
    hourly: pd.DataFrame,
    start: pd.Timestamp,
    out_path: Path,
    *,
    chart_idx: int,
    pmc_map: dict,
    extend_hours: int = 6,
) -> dict:
    """Plot Monday 00:00 NY through Friday end (Saturday 00:00 exclusive)."""
    start = pd.Timestamp(start)
    if start.tzinfo is None:
        start = NY_TZ.localize(start.to_pydatetime())
    else:
        start = start.tz_convert(NY)
    # Snap to Monday 00:00 if caller passed a Monday bar at another hour.
    monday = NY_TZ.localize(datetime.combine(start.date(), time(0, 0)))
    while monday.weekday() != 0:
        monday -= timedelta(days=1)
    start = monday
    end = start + timedelta(days=5)  # Saturday 00:00 — Mon–Fri inclusive

    pre = start - timedelta(hours=1)
    ctx = hourly[(hourly.index >= pre) & (hourly.index < end + timedelta(hours=extend_hours))].copy()
    plot = hourly[(hourly.index >= start) & (hourly.index < end)].copy()
    if len(plot) < 24:
        return {}

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (1.0 / 24.0) * 0.72
    axis_tz = plot.index.tz

    fig, ax = plt.subplots(figsize=(20, 7.5))
    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.7, alpha=0.9, zorder=3)
    price_span = float(plot["high"].max() - plot["low"].min())
    min_body = max(price_span * 0.001, 1e-6)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], candle_colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                alpha=0.85,
                zorder=4,
            )
        )

    if "supertrend" in plot.columns:
        bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
        bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
        ax.plot(plot.index, bull, color="#009c5b", linewidth=2.1, zorder=6, label="ST bull (ATR×3)")
        ax.plot(plot.index, bear, color="#d62728", linewidth=2.1, zorder=6, label="ST bear (ATR×3)")

    segs = _broken_trail_segments(ctx, extend_hours=extend_hours)
    drew_broken_bull = False
    drew_broken_bear = False
    win_lo = float(plot["low"].min())
    win_hi = float(plot["high"].max())
    for seg_start, seg_end, price, side in segs:
        a = max(seg_start, start)
        b = min(seg_end, end + timedelta(hours=extend_hours))
        if b <= a:
            continue
        color = "#009c5b" if side == "bull" else "#d62728"
        label = None
        if side == "bull" and not drew_broken_bull:
            label = "Broken bull trail (+%dh)" % extend_hours
            drew_broken_bull = True
        elif side == "bear" and not drew_broken_bear:
            label = "Broken bear trail (+%dh)" % extend_hours
            drew_broken_bear = True
        ax.plot(
            [a, b],
            [price, price],
            color=color,
            linestyle="--",
            linewidth=1.6,
            alpha=0.9,
            zorder=5,
            label=label,
        )

    # PMC: draw if in range; otherwise annotate above/below without changing scale.
    ts0 = start
    pmc = pmc_map.get((int(ts0.year), int(ts0.month)))
    pmc_drawn = False
    pmc_pos = "n/a"
    pmc_val = None
    if pmc is not None:
        pmc_f = float(pmc)
        pmc_val = pmc_f
        if win_lo <= pmc_f <= win_hi:
            ax.axhline(
                pmc_f,
                color="#1565c0",
                linestyle="--",
                linewidth=1.5,
                zorder=5,
                alpha=0.95,
                label="Prior month close %.5f" % pmc_f,
            )
            pmc_drawn = True
            pmc_pos = "in_range"
        elif pmc_f > win_hi:
            pmc_pos = "above"
        else:
            pmc_pos = "below"

    pad = max(price_span * 0.06, 1e-5)
    ax.set_ylim(win_lo - pad, win_hi + pad)

    if pmc_pos == "above" and pmc_val is not None:
        ax.annotate(
            "PMC ▲ above %.5f" % pmc_val,
            xy=(0.99, 0.98),
            xycoords="axes fraction",
            ha="right",
            va="top",
            fontsize=9,
            color="#1565c0",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#1565c0", alpha=0.9),
            zorder=10,
        )
    elif pmc_pos == "below" and pmc_val is not None:
        ax.annotate(
            "PMC ▼ below %.5f" % pmc_val,
            xy=(0.99, 0.02),
            xycoords="axes fraction",
            ha="right",
            va="bottom",
            fontsize=9,
            color="#1565c0",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#1565c0", alpha=0.9),
            zorder=10,
        )

    day_label = start.strftime("%Y-%m-%d")
    end_label = (end - timedelta(hours=1)).strftime("%Y-%m-%d")  # Friday
    if pmc_drawn:
        pmc_note = " | PMC on (%.5f)" % pmc_val
    elif pmc_pos == "above":
        pmc_note = " | PMC above (hidden %.5f)" % pmc_val
    elif pmc_pos == "below":
        pmc_note = " | PMC below (hidden %.5f)" % pmc_val
    else:
        pmc_note = " | PMC n/a"
    ax.set_title(
        "EURUSD hourly — #%03d | Mon %s → Fri %s | ST ATR(%d)×%g%s"
        % (chart_idx, day_label, end_label, ATR_LEN, ATR_MULT, pmc_note),
        fontsize=10,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
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
        "start": day_label,
        "end": end_label,
        "pmc_drawn": pmc_drawn,
        "pmc_pos": pmc_pos,
        "pmc_val": pmc_val,
        "n_broken": len([s for s in segs if s[0] < end and s[1] > start]),
        "path": out_path.name,
    }


def monday_candidates(hourly: pd.DataFrame) -> List[pd.Timestamp]:
    """Return Monday 00:00 NY timestamps that have a full Mon–Fri ahead."""
    idx = hourly.index
    if idx.tz is None:
        raise ValueError("hourly index must be tz-aware")
    mondays: List[pd.Timestamp] = []
    seen = set()
    for ts in idx:
        ny = ts.tz_convert(NY) if ts.tzinfo else NY_TZ.localize(ts.to_pydatetime())
        if ny.weekday() != 0:
            continue
        monday0 = pd.Timestamp(NY_TZ.localize(datetime.combine(ny.date(), time(0, 0))))
        key = monday0.value
        if key in seen:
            continue
        seen.add(key)
        friday_end = monday0 + timedelta(days=5)
        if friday_end > idx[-1] + timedelta(hours=1):
            continue
        week = hourly[(hourly.index >= monday0) & (hourly.index < friday_end)]
        if len(week) < 24:
            continue
        mondays.append(monday0)
    return mondays


def pick_starts(
    hourly: pd.DataFrame,
    *,
    n: int,
    seed: int,
    prefer_flips: bool,
) -> List[pd.Timestamp]:
    """Sample Monday starts only (Mon–Fri weeks)."""
    candidates = monday_candidates(hourly)
    if len(candidates) < n:
        return list(candidates)

    rng = random.Random(seed)
    if prefer_flips and "supertrend_trend" in hourly.columns:
        trend = hourly["supertrend_trend"]
        flip_times = hourly.index[(trend != trend.shift(1)) & trend.notna() & trend.shift(1).notna()]
        scored = []
        for m in candidates:
            end = m + timedelta(days=5)
            n_flips = int(((flip_times >= m) & (flip_times < end)).sum())
            scored.append((n_flips, pd.Timestamp(m)))
        scored.sort(key=lambda t: (-t[0], int(pd.Timestamp(t[1]).value)))
        with_flips = [m for n_flips, m in scored if n_flips > 0]
        if len(with_flips) >= n:
            step = max(1, len(with_flips) // n)
            picked = with_flips[::step][:n]
            if len(picked) < n:
                pool = [m for m in with_flips if m not in set(picked)]
                picked.extend(rng.sample(pool, min(n - len(picked), len(pool))))
            return sorted(picked[:n])
        remaining = n - len(with_flips)
        pool = [m for n_flips, m in scored if n_flips == 0]
        step = max(1, len(pool) // max(1, remaining))
        extra = pool[::step][:remaining]
        return sorted(with_flips + extra)[:n]

    step = max(1, len(candidates) // n)
    picked = list(candidates[::step][:n])
    if len(picked) < n:
        pool = [c for c in candidates if c not in set(picked)]
        picked.extend(rng.sample(pool, min(n - len(picked), len(pool))))
    return sorted(picked[:n])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--extend-hours", type=int, default=6)
    parser.add_argument("--prefer-flips", action="store_true", default=True)
    parser.add_argument("--no-prefer-flips", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    prefer_flips = bool(args.prefer_flips) and not bool(args.no_prefer_flips)

    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD 1m → hourly SuperTrend...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    hourly = compute_supertrend(
        resample_hourly(concat_all_1m(bars_by_day)),
        atr_len=ATR_LEN,
        multiplier=ATR_MULT,
    )
    if hourly.index.tz is None:
        hourly.index = hourly.index.tz_localize(NY)
    else:
        hourly.index = hourly.index.tz_convert(NY)
    pmc_map = load_prev_month_close_map(daily_path)
    print("  %s hourly bars" % f"{len(hourly):,}", flush=True)

    starts = pick_starts(hourly, n=args.n, seed=args.seed, prefer_flips=prefer_flips)
    print("  %d Monday–Friday weeks selected" % len(starts), flush=True)
    charts_dir = args.output_root / "charts"
    if charts_dir.exists():
        for p in charts_dir.glob("*.png"):
            p.unlink()
    charts_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, start in enumerate(starts, start=1):
        stamp = start.strftime("%Y-%m-%d")
        out_path = charts_dir / ("%03d_%s.png" % (i, stamp))
        meta = plot_window(
            hourly,
            start,
            out_path,
            chart_idx=i,
            pmc_map=pmc_map,
            extend_hours=args.extend_hours,
        )
        if meta:
            rows.append(meta)
        if i % 25 == 0:
            print("  wrote %d/%d" % (i, len(starts)), flush=True)

    pmc_on = sum(1 for r in rows if r["pmc_drawn"])
    pmc_above = sum(1 for r in rows if r.get("pmc_pos") == "above")
    pmc_below = sum(1 for r in rows if r.get("pmc_pos") == "below")

    def pmc_label(r: dict) -> str:
        pos = r.get("pmc_pos", "n/a")
        val = r.get("pmc_val")
        if pos == "in_range":
            return "on (%.5f)" % val if val is not None else "on"
        if pos == "above":
            return "above (%.5f)" % val if val is not None else "above"
        if pos == "below":
            return "below (%.5f)" % val if val is not None else "below"
        return "n/a"

    lines = [
        "# EURUSD hourly ST + PMC context charts",
        "",
        "**%d** weeks (**Monday → Friday** NY), seed `%d`. No trades." % (len(rows), args.seed),
        "",
        "- Hourly candles",
        "- SuperTrend ATR(%d)×%g (solid bull/bear)" % (ATR_LEN, ATR_MULT),
        "- Broken trailing stops extended **%dh** as dashed lines" % args.extend_hours,
        "- PMC drawn only when inside candle range (**%d** on-chart); "
        "hidden cases labeled **above** (%d) or **below** (%d)"
        % (pmc_on, pmc_above, pmc_below),
        "",
        "| # | Mon | Fri | PMC | Broken trails | Chart |",
        "|---:|---|---|---|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| %d | %s | %s | %s | %d | [charts/%s](charts/%s) |"
            % (
                r["idx"],
                r["start"],
                r.get("end", ""),
                pmc_label(r),
                r["n_broken"],
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d charts → %s" % (len(rows), args.output_root), flush=True)
    print(
        "PMC on=%d above=%d below=%d" % (pmc_on, pmc_above, pmc_below),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
