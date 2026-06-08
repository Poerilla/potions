from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional

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

from potions.live.v2b_strategy_cross_market_replay import _rth_bars, load_1m_by_ny_date_any  # noqa: E402


def compute_supertrend(df: pd.DataFrame, atr_len: int = 14, multiplier: float = 3.0) -> pd.DataFrame:
    out = df.copy()
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1.0 / float(atr_len), adjust=False, min_periods=atr_len).mean()
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = pd.Series(index=out.index, dtype="float64")
    final_lower = pd.Series(index=out.index, dtype="float64")
    trend = pd.Series(index=out.index, dtype="int64")
    st = pd.Series(index=out.index, dtype="float64")

    for i in range(len(out)):
        if i == 0 or pd.isna(atr.iloc[i]):
            final_upper.iloc[i] = basic_upper.iloc[i]
            final_lower.iloc[i] = basic_lower.iloc[i]
            trend.iloc[i] = 1
            st.iloc[i] = np.nan
            continue

        prev_i = i - 1
        if (
            pd.isna(final_upper.iloc[prev_i])
            or basic_upper.iloc[i] < final_upper.iloc[prev_i]
            or close.iloc[prev_i] > final_upper.iloc[prev_i]
        ):
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[prev_i]

        if (
            pd.isna(final_lower.iloc[prev_i])
            or basic_lower.iloc[i] > final_lower.iloc[prev_i]
            or close.iloc[prev_i] < final_lower.iloc[prev_i]
        ):
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[prev_i]

        prev_trend = int(trend.iloc[prev_i]) if not pd.isna(trend.iloc[prev_i]) else 1
        if prev_trend == 1:
            trend.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
        else:
            trend.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        st.iloc[i] = final_lower.iloc[i] if trend.iloc[i] == 1 else final_upper.iloc[i]

    out["atr"] = atr
    out["supertrend"] = st
    out["supertrend_trend"] = trend
    return out


def resample_ohlcv_by_rows(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes <= 1:
        return df.copy()
    groups = np.arange(len(df)) // int(minutes)
    out = df.groupby(groups).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    out.index = df.groupby(groups).apply(lambda item: item.index[-1])
    return out


def supertrend_overlay(df_1m: pd.DataFrame, minutes: int, atr_len: int, multiplier: float) -> pd.DataFrame:
    st_bars = resample_ohlcv_by_rows(df_1m, minutes)
    st = compute_supertrend(st_bars, atr_len=atr_len, multiplier=multiplier)[
        ["supertrend", "supertrend_trend"]
    ]
    overlay = st.reindex(df_1m.index, method="ffill")
    return overlay


def plot_day(
    day: str,
    df: pd.DataFrame,
    out_path: Path,
    atr_len: int,
    multiplier: float,
    supertrend_minutes: int,
) -> None:
    plot = df.copy()
    overlay = supertrend_overlay(
        plot,
        minutes=supertrend_minutes,
        atr_len=atr_len,
        multiplier=multiplier,
    )
    plot["supertrend"] = overlay["supertrend"]
    plot["supertrend_trend"] = overlay["supertrend_trend"]
    x = mdates.date2num(plot.index.to_pydatetime())
    width = (1.0 / (24.0 * 60.0)) * 0.72
    fig, (ax, vol_ax) = plt.subplots(
        2,
        1,
        figsize=(17, 9),
        gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        sharex=True,
    )
    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")

    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.75, alpha=0.9)
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
            )
        )

    bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
    bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
    label_prefix = f"{supertrend_minutes}m ATR Supertrend"
    ax.plot(plot.index, bull, color="#009c5b", linewidth=2.4, zorder=6, label=f"{label_prefix} bullish")
    ax.plot(plot.index, bear, color="#d62728", linewidth=2.4, zorder=6, label=f"{label_prefix} bearish")

    ax.set_title(
        f"YM 1m RTH candles with {supertrend_minutes}m ATR Supertrend - "
        f"{day} - ATR({atr_len}) x {multiplier:g}"
    )
    ax.set_ylabel("YM price")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=9)

    vol_ax.bar(plot.index, plot.get("volume", 0), width=width, color=candle_colors, alpha=0.5)
    vol_ax.set_ylabel("Vol")
    vol_ax.grid(True, axis="y", color="#e2e2e2", linewidth=0.6, alpha=0.75)
    axis_tz = plot.index.tz
    vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=axis_tz))
    vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=axis_tz))
    vol_ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def write_index(
    out_root: Path,
    sampled_days: List[str],
    atr_len: int,
    multiplier: float,
    seed: int,
    supertrend_minutes: int,
) -> None:
    lines = [
        f"# YM 1m Candles With {supertrend_minutes}m ATR Supertrend Random Sample",
        "",
        f"Sample: `{len(sampled_days)}` RTH sessions.",
        f"Seed: `{seed}`.",
        f"Candles: `1-minute` YM RTH bars.",
        f"Indicator: `ATR({atr_len}) x {multiplier:g}` Supertrend on `{supertrend_minutes}-minute` RTH bars.",
        "Timezone: `America/New_York`.",
        "",
        "| # | Day | Chart |",
        "|---:|---|---|",
    ]
    for idx, day in enumerate(sampled_days, start=1):
        rel = f"charts/{idx:02d}_{day}.png"
        lines.append(f"| {idx} | {day} | [{rel}]({rel}) |")
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build random YM 1m candle charts with ATR Supertrend overlays.")
    parser.add_argument("--dbn", type=Path, default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst")
    parser.add_argument("--out-root", type=Path, default=REPO / "ym" / "case_studies" / "ym_1m_atr_supertrend_random_50")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--multiplier", type=float, default=3.0)
    parser.add_argument("--supertrend-minutes", type=int, default=1)
    args = parser.parse_args(argv)
    if args.supertrend_minutes < 1:
        raise SystemExit("--supertrend-minutes must be >= 1")

    gby = load_1m_by_ny_date_any(args.dbn.resolve(), "ym")
    rng = random.Random(args.seed)
    candidates = sorted(gby)
    rng.shuffle(candidates)
    full_days: Dict[str, pd.DataFrame] = {}
    for day in candidates:
        rth = _rth_bars(gby.get(day), day)
        if len(rth) >= 350:
            full_days[day.isoformat()] = rth
        if len(full_days) >= args.sample_size:
            break
    sampled_days = sorted(full_days)
    if len(sampled_days) < args.sample_size:
        raise SystemExit(f"Only {len(sampled_days)} full-ish RTH days available; need {args.sample_size}.")

    charts_dir = args.out_root / "charts"
    for idx, day in enumerate(sampled_days, start=1):
        out_path = charts_dir / f"{idx:02d}_{day}.png"
        if out_path.exists():
            continue
        plot_day(day, full_days[day], out_path, args.atr_len, args.multiplier, args.supertrend_minutes)
        if idx % 10 == 0:
            print(f"Built {idx}/{len(sampled_days)} YM charts", flush=True)
    write_index(args.out_root, sampled_days, args.atr_len, args.multiplier, args.seed, args.supertrend_minutes)
    print(f"Wrote {args.out_root / 'INDEX.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
