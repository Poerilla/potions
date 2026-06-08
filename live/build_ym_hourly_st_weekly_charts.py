from __future__ import annotations

import argparse
import calendar
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"

sys.path[:0] = [str(REPO.parent), str(MNQ_ROOT), str(SCRIPTS), str(CASE)]

from potions.live.build_ym_1m_atr_supertrend_sample import compute_supertrend  # noqa: E402
from potions.live.v2b_strategy_cross_market_replay import load_1m_by_ny_date_any  # noqa: E402


@dataclass
class MonthWeekSpec:
    year: int
    month: int
    target_monday: date
    prev_monday: date
    prev_month_close: float


def week_days(monday: date) -> List[date]:
    return [monday + timedelta(days=i) for i in range(7)]


def first_monday_of_month(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def day_bars(gby: Dict[date, pd.DataFrame], session_day: date) -> pd.DataFrame:
    df = gby.get(session_day)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.sort_index()


def concat_days(gby: Dict[date, pd.DataFrame], days: Sequence[date]) -> pd.DataFrame:
    parts = [day_bars(gby, d) for d in days]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def resample_hourly(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m.empty:
        return df_1m
    return (
        df_1m.resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def load_prev_month_closes(daily_path: Path) -> pd.DataFrame:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    last = daily.groupby(["year", "month"], as_index=False).tail(1)
    return last.set_index(["year", "month"])["close"]


def warmup_days_before(start: date, gby: Dict[date, pd.DataFrame], count: int) -> List[date]:
    prior: List[date] = []
    cursor = start - timedelta(days=1)
    while len(prior) < count:
        if cursor in gby and len(day_bars(gby, cursor)) >= 30:
            prior.append(cursor)
        cursor -= timedelta(days=1)
        if (start - cursor).days > 120:
            break
    return sorted(prior)


def month_week_spec(
    year: int,
    month: int,
    gby: Dict[date, pd.DataFrame],
    prev_closes: pd.Series,
    *,
    min_day_bars: int,
) -> Optional[MonthWeekSpec]:
    target_monday = first_monday_of_month(year, month)
    prev_monday = target_monday - timedelta(days=7)
    plot_days = week_days(prev_monday) + week_days(target_monday)
    for d in plot_days:
        n = len(day_bars(gby, d))
        if d.weekday() < 5 and n < min_day_bars:
            return None

    prior_year, prior_month = (year, month - 1) if month > 1 else (year - 1, 12)
    try:
        prev_close = float(prev_closes.loc[(prior_year, prior_month)])
    except KeyError:
        return None
    if not np.isfinite(prev_close):
        return None
    return MonthWeekSpec(year, month, target_monday, prev_monday, prev_close)


def candidate_months(
    gby: Dict[date, pd.DataFrame],
    prev_closes: pd.Series,
    *,
    min_day_bars: int,
) -> List[MonthWeekSpec]:
    out: List[MonthWeekSpec] = []
    dates = sorted(gby)
    if not dates:
        return out
    y0, y1 = dates[0].year, dates[-1].year
    for year in range(y0, y1 + 1):
        for month in range(1, 13):
            spec = month_week_spec(year, month, gby, prev_closes, min_day_bars=min_day_bars)
            if spec is not None:
                out.append(spec)
    return out


def hourly_supertrend_for_spec(
    gby: Dict[date, pd.DataFrame],
    spec: MonthWeekSpec,
    *,
    warmup_days_count: int,
    atr_len: int,
    atr_mult: float,
) -> pd.DataFrame:
    plot_days = week_days(spec.prev_monday) + week_days(spec.target_monday)
    warm = warmup_days_before(spec.prev_monday, gby, warmup_days_count)
    one_m = concat_days(gby, warm + plot_days)
    hourly = resample_hourly(one_m)
    if hourly.empty:
        return hourly
    st = compute_supertrend(hourly, atr_len=atr_len, multiplier=atr_mult)
    plot_start = pd.Timestamp(f"{spec.prev_monday.isoformat()}", tz=hourly.index.tz)
    plot_end = hourly.index.max()
    return st[(st.index >= plot_start) & (st.index <= plot_end)].copy()


def plot_spec(
    df: pd.DataFrame,
    spec: MonthWeekSpec,
    out_path: Path,
    *,
    atr_len: int,
    atr_mult: float,
) -> None:
    plot = df.copy()
    x = mdates.date2num(plot.index.to_pydatetime())
    width = (1.0 / 24.0) * 0.72
    target_end = spec.target_monday + timedelta(days=6)
    axis_tz = plot.index.tz
    target_start_ts = pd.Timestamp(f"{spec.target_monday.isoformat()}", tz=axis_tz)
    target_end_ts = pd.Timestamp(f"{target_end.isoformat()} 23:59:59", tz=axis_tz)

    fig, (ax, vol_ax) = plt.subplots(
        2,
        1,
        figsize=(20, 9),
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        sharex=True,
    )
    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")

    ax.axvspan(
        mdates.date2num(target_start_ts.to_pydatetime()),
        mdates.date2num(target_end_ts.to_pydatetime()),
        color="#fff3cd",
        alpha=0.35,
        zorder=0,
        label="First week of month",
    )

    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.9, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], candle_colors):
        bottom = min(o, c)
        height = max(abs(c - o), 0.01)
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

    bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
    bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
    ax.plot(plot.index, bull, color="#009c5b", linewidth=2.6, zorder=6, label="Hourly ST bullish stop")
    ax.plot(plot.index, bear, color="#d62728", linewidth=2.6, zorder=6, label="Hourly ST bearish stop")

    ax.axhline(
        spec.prev_month_close,
        color="#1565c0",
        linestyle="--",
        linewidth=1.6,
        zorder=5,
        alpha=0.95,
        label=f"Prior month close ({spec.prev_month_close:,.0f})",
    )

    y_top = float(plot["high"].max())
    for monday, label in (
        (spec.prev_monday, "prev wk"),
        (spec.target_monday, calendar.month_abbr[spec.month]),
    ):
        t0 = pd.Timestamp(f"{monday.isoformat()}", tz=axis_tz)
        ax.axvline(mdates.date2num(t0.to_pydatetime()), color="#888888", linewidth=1.0, linestyle=":", alpha=0.9)
        ax.text(
            mdates.date2num(t0.to_pydatetime()),
            y_top,
            f"{label}\n{monday.strftime('%m-%d')}",
            fontsize=7,
            color="#555555",
            ha="left",
            va="top",
        )

    month_name = calendar.month_name[spec.month]
    ax.set_title(
        f"YM hourly (all sessions) — {month_name} {spec.year} first week "
        f"({spec.target_monday.isoformat()} – {target_end.isoformat()}) "
        f"+ prior week — ATR({atr_len}) x {atr_mult:g} Supertrend"
    )
    ax.set_ylabel("YM price")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8)

    vol_ax.bar(plot.index, plot.get("volume", 0), width=width, color=candle_colors, alpha=0.5)
    vol_ax.set_ylabel("Vol")
    vol_ax.grid(True, axis="y", color="#e2e2e2", linewidth=0.6, alpha=0.75)
    vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=axis_tz))
    vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=axis_tz))
    vol_ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def write_index(
    out_root: Path,
    specs: List[MonthWeekSpec],
    *,
    seed: int,
    atr_len: int,
    atr_mult: float,
    warmup_days_count: int,
) -> None:
    lines = [
        "# YM Hourly Supertrend — First Week Of Month (with prior week context)",
        "",
        f"Sample: `{len(specs)}` months (first calendar week of each, plus prior week).",
        f"Seed: `{seed}`.",
        "Candles: every `1-hour` bar that prints from YM 1-minute data (all available hours).",
        f"Indicator: `ATR({atr_len}) x {atr_mult:g}` Supertrend on hourly bars "
        f"(warmup: `{warmup_days_count}` calendar days before prior week).",
        "Reference: dashed blue line = prior calendar month closing price (daily CSV).",
        "Shaded band = first week of the target month.",
        "Timezone: `America/New_York`.",
        "",
        "| # | Month | First week (Mon) | Prior month close | Chart |",
        "|---:|---|---|---:|---|",
    ]
    for idx, spec in enumerate(specs, start=1):
        rel = f"charts/{idx:02d}_{spec.year}-{spec.month:02d}.png"
        month_label = f"{calendar.month_name[spec.month]} {spec.year}"
        lines.append(
            f"| {idx} | {month_label} | {spec.target_monday.isoformat()} | "
            f"{spec.prev_month_close:,.0f} | [{rel}]({rel}) |"
        )
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build YM hourly charts: prior week + first week of month with Supertrend."
    )
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument(
        "--daily",
        type=Path,
        default=REPO / "ym" / "ym_daily.csv",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_hourly_st_first_week_monthly_15",
    )
    parser.add_argument("--sample-size", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--warmup-days", type=int, default=14)
    parser.add_argument("--min-day-bars", type=int, default=30)
    args = parser.parse_args(argv)

    if args.out_root.exists():
        shutil.rmtree(args.out_root)
    args.out_root.mkdir(parents=True, exist_ok=True)

    old_random = REPO / "ym" / "case_studies" / "ym_hourly_st_trailing_random_15"
    if old_random.exists():
        shutil.rmtree(old_random)
        print(f"Removed old charts: {old_random}", flush=True)

    print("Loading YM 1m DBN...", flush=True)
    gby = load_1m_by_ny_date_any(args.dbn.resolve(), "ym")
    prev_closes = load_prev_month_closes(args.daily)
    candidates = candidate_months(gby, prev_closes, min_day_bars=args.min_day_bars)
    if len(candidates) < args.sample_size:
        raise SystemExit(f"Only {len(candidates)} valid months; need {args.sample_size}.")

    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    picked = sorted(candidates[: args.sample_size], key=lambda s: (s.year, s.month))

    charts_dir = args.out_root / "charts"
    for idx, spec in enumerate(picked, start=1):
        out_path = charts_dir / f"{idx:02d}_{spec.year}-{spec.month:02d}.png"
        hourly = hourly_supertrend_for_spec(
            gby,
            spec,
            warmup_days_count=args.warmup_days,
            atr_len=args.atr_len,
            atr_mult=args.atr_mult,
        )
        if hourly.empty:
            print(f"Skip empty month {spec.year}-{spec.month:02d}", flush=True)
            continue
        plot_spec(hourly, spec, out_path, atr_len=args.atr_len, atr_mult=args.atr_mult)
        print(f"Built {idx}/{len(picked)}: {out_path.name}", flush=True)

    write_index(
        args.out_root,
        picked,
        seed=args.seed,
        atr_len=args.atr_len,
        atr_mult=args.atr_mult,
        warmup_days_count=args.warmup_days,
    )
    print(f"Wrote {args.out_root / 'INDEX.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
