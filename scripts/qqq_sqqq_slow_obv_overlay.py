#!/usr/bin/env python3
"""QQQ vs SQQQ slow-OBV overlay chart.

This is a visual research helper. It plots QQQ and SQQQ normalized adjusted
closes on the same axis and overlays the slow OBV cross markers most relevant
to the inverse thesis:

- QQQ bearish OBV cross
- SQQQ bullish OBV cross

SQQQ is the 3x inverse Nasdaq-100 ETF proxy. The adjusted close line includes
daily reset decay and reverse split adjustments.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from etf_obv_bearish_dca_study import add_obv
from qqq_yearly_orb_study import load_adjusted_daily


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_sqqq_slow_obv_overlay"
DEFAULT_START = "2010-01-01"


def money(value: float) -> str:
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.0f"))


def pct(value: float) -> str:
    return "%.2f%%" % value


def default_completed_end(today: dt.date | None = None) -> str:
    day = (today or dt.date.today()) - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day.isoformat()


def obv_axis_scale(values: pd.Series) -> tuple[float, str]:
    max_abs = float(pd.to_numeric(values, errors="coerce").abs().max())
    if not math.isfinite(max_abs) or max_abs == 0:
        return 1.0, "OBV"
    if max_abs >= 1e9:
        return 1e9, "OBV / 1B"
    if max_abs >= 1e6:
        return 1e6, "OBV / 1M"
    if max_abs >= 1e3:
        return 1e3, "OBV / 1K"
    return 1.0, "OBV"


def common_window(data: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    starts = [pd.Timestamp(df["date"].min()) for df in data.values()]
    ends = [pd.Timestamp(df["date"].max()) for df in data.values()]
    return max(starts), min(ends)


def restrict_common(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    start, end = common_window(data)
    out: dict[str, pd.DataFrame] = {}
    date_sets = []
    for ticker, df in data.items():
        work = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        work = work.sort_values("date").reset_index(drop=True)
        date_sets.append(set(pd.to_datetime(work["date"])))
        out[ticker] = work
    dates = sorted(set.intersection(*date_sets))
    date_set = set(dates)
    for ticker, df in out.items():
        work = df[df["date"].isin(date_set)].copy().reset_index(drop=True)
        work["norm_close"] = work["close"] / float(work.iloc[0]["close"]) * 100.0
        out[ticker] = work
    return out


def overlap_within_days(left_dates: list[pd.Timestamp], right_dates: list[pd.Timestamp], days: int) -> int:
    right = sorted(pd.Timestamp(d) for d in right_dates)
    if not right:
        return 0
    count = 0
    for left in sorted(pd.Timestamp(d) for d in left_dates):
        if any(abs((candidate - left).days) <= days for candidate in right):
            count += 1
    return count


def summarize(ticker: str, daily: pd.DataFrame) -> dict[str, object]:
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    start_close = float(daily.iloc[0]["close"])
    end_close = float(daily.iloc[-1]["close"])
    bull = int(daily["obv_bull_cross"].sum())
    bear = int(daily["obv_bear_cross"].sum())
    return {
        "ticker": ticker,
        "start": pd.Timestamp(daily.iloc[0]["date"]).date().isoformat(),
        "end": pd.Timestamp(daily.iloc[-1]["date"]).date().isoformat(),
        "start_close": start_close,
        "end_close": end_close,
        "close_return_pct": (end_close / start_close - 1.0) * 100.0 if start_close else math.nan,
        "obv_bull_crosses": bull,
        "obv_bear_crosses": bear,
        "bull_crosses_per_year": bull / years,
        "bear_crosses_per_year": bear / years,
    }


def plot_overlay(data: dict[str, pd.DataFrame], out_path: Path, obv_ma: int, last_bars: int | None) -> None:
    qqq = data["QQQ"].copy()
    sqqq = data["SQQQ"].copy()
    if last_bars is not None:
        qqq = qqq.tail(last_bars).copy()
        sqqq = sqqq[sqqq["date"].isin(set(qqq["date"]))].copy()
    qqq_bear = qqq[qqq["obv_bear_cross"]]
    sqqq_bull = sqqq[sqqq["obv_bull_cross"]]

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        sharex=True,
        height_ratios=[2.2, 1.05, 1.05],
    )
    ax_price, ax_qqq, ax_sqqq = axes

    ax_price.plot(qqq["date"], qqq["norm_close"], color="#2563eb", linewidth=1.8, label="QQQ normalized adj close")
    ax_price.plot(sqqq["date"], sqqq["norm_close"], color="#dc2626", linewidth=1.5, label="SQQQ normalized adj close")
    ax_price.scatter(
        qqq_bear["date"],
        qqq_bear["norm_close"],
        color="#991b1b",
        marker="v",
        s=34,
        label="QQQ OBV bear cross",
        zorder=5,
    )
    ax_price.scatter(
        sqqq_bull["date"],
        sqqq_bull["norm_close"],
        color="#047857",
        marker="^",
        s=34,
        label="SQQQ OBV bull cross",
        zorder=5,
    )
    ax_price.set_yscale("log")
    ax_price.set_ylabel("Normalized adj close\nlog scale")
    ax_price.grid(True, alpha=0.25)
    title_span = "recent %d bars" % last_bars if last_bars else "full common history"
    ax_price.set_title("QQQ vs SQQQ with slow OBV crosses (%d-day SMA, %s)" % (obv_ma, title_span))
    ax_price.legend(loc="upper left", ncols=2, fontsize=8)

    qqq_scale, qqq_label = obv_axis_scale(qqq["obv"])
    qqq_obv = qqq["obv"] / qqq_scale
    qqq_ma = qqq["obv_ma"] / qqq_scale
    ax_qqq.plot(qqq["date"], qqq_obv, color="#2563eb", linewidth=1.1, label="QQQ OBV")
    ax_qqq.plot(qqq["date"], qqq_ma, color="#f97316", linewidth=1.0, label="QQQ OBV SMA%d" % obv_ma)
    qqq_bear_obv = qqq_bear["obv"] / qqq_scale
    ax_qqq.scatter(qqq_bear["date"], qqq_bear_obv, color="#991b1b", marker="v", s=22, zorder=5)
    ax_qqq.set_ylabel(qqq_label)
    ax_qqq.grid(True, alpha=0.25)
    ax_qqq.legend(loc="upper left", fontsize=8)

    sqqq_scale, sqqq_label = obv_axis_scale(sqqq["obv"])
    sqqq_obv = sqqq["obv"] / sqqq_scale
    sqqq_ma = sqqq["obv_ma"] / sqqq_scale
    ax_sqqq.plot(sqqq["date"], sqqq_obv, color="#dc2626", linewidth=1.1, label="SQQQ OBV")
    ax_sqqq.plot(sqqq["date"], sqqq_ma, color="#f97316", linewidth=1.0, label="SQQQ OBV SMA%d" % obv_ma)
    sqqq_bull_obv = sqqq_bull["obv"] / sqqq_scale
    ax_sqqq.scatter(sqqq_bull["date"], sqqq_bull_obv, color="#047857", marker="^", s=22, zorder=5)
    ax_sqqq.set_ylabel(sqqq_label)
    ax_sqqq.grid(True, alpha=0.25)
    ax_sqqq.legend(loc="upper left", fontsize=8)

    locator = mdates.YearLocator(base=1 if last_bars else 2)
    ax_sqqq.xaxis.set_major_locator(locator)
    ax_sqqq.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(out_dir: Path, data: dict[str, pd.DataFrame], summary: pd.DataFrame, obv_ma: int) -> None:
    qqq_bear_dates = list(data["QQQ"].loc[data["QQQ"]["obv_bear_cross"], "date"])
    sqqq_bull_dates = list(data["SQQQ"].loc[data["SQQQ"]["obv_bull_cross"], "date"])
    overlap_3 = overlap_within_days(qqq_bear_dates, sqqq_bull_dates, 3)
    overlap_5 = overlap_within_days(qqq_bear_dates, sqqq_bull_dates, 5)
    lines = [
        "# QQQ / SQQQ Slow OBV Overlay",
        "",
        "Visual study: QQQ and SQQQ plotted together with slow OBV cross markers.",
        "",
        "- `SQQQ` is used as the inverse leveraged QQQ proxy (3x daily-reset inverse Nasdaq-100 ETF).",
        "- Prices are Yahoo adjusted closes, normalized to the first common trading day, and plotted on a log scale.",
        "- Slow OBV cross uses OBV crossing its `%d`-day simple moving average." % obv_ma,
        "- Markers: QQQ bearish OBV crosses and SQQQ bullish OBV crosses.",
        "- SQQQ is a daily-reset leveraged ETF; the long-term line includes leverage decay and reverse split adjustments.",
        "",
        "Window: **%s through %s**." % (summary["start"].min(), summary["end"].max()),
        "",
        "## Summary",
        "",
        "| Ticker | Start Close | End Close | Adj Close Return | Bull Crosses | Bear Crosses | Bull / Yr | Bear / Yr |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| %s | %s | %s | %s | %d | %d | %.2f | %.2f |"
            % (
                row["ticker"],
                money(float(row["start_close"])),
                money(float(row["end_close"])),
                pct(float(row["close_return_pct"])),
                int(row["obv_bull_crosses"]),
                int(row["obv_bear_crosses"]),
                float(row["bull_crosses_per_year"]),
                float(row["bear_crosses_per_year"]),
            )
        )
    lines.extend(
        [
            "",
            "## Cross Alignment",
            "",
            "- QQQ bearish crosses: **%d**." % len(qqq_bear_dates),
            "- SQQQ bullish crosses: **%d**." % len(sqqq_bull_dates),
            "- QQQ bearish crosses with a SQQQ bullish cross within 3 calendar days: **%d**." % overlap_3,
            "- QQQ bearish crosses with a SQQQ bullish cross within 5 calendar days: **%d**." % overlap_5,
            "",
            "## Charts",
            "",
            "- Full common history: [`charts/qqq_sqqq_slow_obv_full.png`](charts/qqq_sqqq_slow_obv_full.png)",
            "- Recent zoom: [`charts/qqq_sqqq_slow_obv_recent.png`](charts/qqq_sqqq_slow_obv_recent.png)",
            "",
            "## Outputs",
            "",
            "- `summary.csv`",
            "- `QQQ_slow_obv_daily.csv`",
            "- `SQQQ_slow_obv_daily.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot QQQ and SQQQ with slow OBV cross markers.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--obv-ma", type=int, default=200)
    parser.add_argument("--recent-bars", type=int, default=760)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    raw = {}
    for ticker in ["QQQ", "SQQQ"]:
        daily = load_adjusted_daily(ticker, args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
        raw[ticker] = add_obv(daily, args.obv_ma)
    data = restrict_common(raw)

    summary = pd.DataFrame([summarize(ticker, daily) for ticker, daily in data.items()])
    summary.to_csv(out_dir / "summary.csv", index=False)
    for ticker, daily in data.items():
        daily.to_csv(out_dir / ("%s_slow_obv_daily.csv" % ticker), index=False)

    plot_overlay(data, out_dir / "charts" / "qqq_sqqq_slow_obv_full.png", args.obv_ma, last_bars=None)
    plot_overlay(data, out_dir / "charts" / "qqq_sqqq_slow_obv_recent.png", args.obv_ma, last_bars=args.recent_bars)
    write_report(out_dir, data, summary, args.obv_ma)
    print("Wrote %s" % (out_dir / "INDEX.md"))


if __name__ == "__main__":
    main()
