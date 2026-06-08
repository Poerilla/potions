from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .nq_15m_ma200_supertrend_100_week_charts import plot_candles, shade_rth
from .nq_ma500_retest_weekly_replay import weekly_c3_info, weekly_ohlc
from .nq_weekly_mid_ma500_bias_replay import to_hourly_with_ma
from .weekly_mid_ma500_bias_broker_like_charts import read_bars, read_units
from .ym_weekly_chart_context import compute_weekly_context, draw_weekly_context_panel


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
ATR_LEN = 14
ATR_MULT = 3.0


def hourly_with_atr(bars: pd.DataFrame, *, atr_len: int = ATR_LEN) -> pd.DataFrame:
    hourly = (
        bars.resample("1h", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    prev_close = hourly["close"].shift(1)
    tr = pd.concat(
        [
            hourly["high"] - hourly["low"],
            (hourly["high"] - prev_close).abs(),
            (hourly["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    hourly["atr"] = tr.ewm(alpha=1.0 / float(atr_len), adjust=False, min_periods=atr_len).mean()
    return hourly


def plot_week_pwc_atr(
    out_path: Path,
    week_15m: pd.DataFrame,
    week_1h: pd.DataFrame,
    week_hourly_atr: pd.DataFrame,
    week_start: pd.Timestamp,
    prev_levels: dict[str, float],
    trades: pd.DataFrame,
    c3_info: Optional[dict[str, object]],
    title: str,
    weekly_context: Optional[dict[str, object]],
    *,
    atr_mult: float = ATR_MULT,
) -> None:
    week_end = week_start + pd.Timedelta(days=7)
    pwc = float(prev_levels["prev_close"])
    if weekly_context is not None:
        weekly_context = dict(weekly_context)
        weekly_context["shown_week"] = week_start.date().isoformat()
        fig = plt.figure(figsize=(20, 9.5))
        gs = fig.add_gridspec(2, 2, height_ratios=[4, 1], width_ratios=[1.0, 1.8], hspace=0.08, wspace=0.06)
        ax = fig.add_subplot(gs[0, :])
    else:
        fig, ax = plt.subplots(1, 1, figsize=(20, 8))

    shade_rth(ax, week_start, week_end)
    plot_candles(ax, week_1h, width_days=(60 / (24 * 60)) * 0.68)
    ax.plot(week_15m.index, week_15m["ma500"], color="#1f3a93", linewidth=1.55, label="15m MA500")

    ctx = week_hourly_atr[(week_hourly_atr.index >= week_start) & (week_hourly_atr.index < week_end)].copy()
    if not ctx.empty and ctx["atr"].notna().any():
        ctx["pwc_upper"] = pwc + atr_mult * ctx["atr"]
        ctx["pwc_lower"] = pwc - atr_mult * ctx["atr"]
        ax.plot(ctx.index, ctx["pwc_upper"], color="#00838f", linewidth=1.15, linestyle="-.", alpha=0.9, label="PWC + 3xATR")
        ax.plot(ctx.index, ctx["pwc_lower"], color="#00838f", linewidth=1.15, linestyle="-.", alpha=0.9, label="PWC - 3xATR")

    specs = [
        ("prev_high", "PWH", "#7b1fa2", "-"),
        ("prev_low", "PWL", "#7b1fa2", "-"),
        ("prev_mid", "PW 50%", "#555555", "--"),
        ("prev_close", "PWC", "#f57c00", "-."),
    ]
    x_text = week_1h.index[0] + (week_1h.index[-1] - week_1h.index[0]) * 0.01
    for key, label, color, linestyle in specs:
        value = prev_levels[key]
        ax.axhline(value, color=color, linestyle=linestyle, linewidth=1.0, alpha=0.82, label=label)
        ax.text(x_text, value, "%s %.2f" % (label, value), color=color, fontsize=7, va="bottom", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 1.0})

    if not ctx.empty and ctx["atr"].notna().any():
        last = ctx.dropna(subset=["atr"]).iloc[-1]
        for value, label in [
            (pwc + atr_mult * float(last["atr"]), "PWC+3ATR"),
            (pwc - atr_mult * float(last["atr"]), "PWC-3ATR"),
        ]:
            ax.text(x_text, value, "%s %.2f" % (label, value), color="#00838f", fontsize=7, va="bottom", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 1.0})

    if not trades.empty:
        for _, tr in trades.iterrows():
            color = "#008c5a" if tr["side"] == "long" else "#c62828"
            marker = "^" if tr["side"] == "long" else "v"
            ax.scatter([tr["entry_ts"]], [tr["entry_price"]], color=color, marker=marker, s=46, zorder=8)
            ax.scatter([tr["exit_ts"]], [tr["exit_price"]], color="#111111", marker="x", s=46, zorder=8)
            ax.plot([tr["entry_ts"], tr["exit_ts"]], [tr["entry_price"], tr["exit_price"]], color=color, linewidth=0.9, alpha=0.7)

    title_color = "#222222"
    c3_label = "No weekly C3"
    if c3_info:
        title_color = "#008c5a" if c3_info["direction"] == "bullish" else "#c62828"
        c3_label = "Weekly C3 %s %s" % (str(c3_info["direction"]).upper(), "hit" if c3_info["hit"] else "miss")
    ax.set_title("%s - %s" % (title, c3_label), color=title_color)
    ax.set_ylabel("YM")
    ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=8, tz=week_1h.index.tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M", tz=week_1h.index.tz))
    for label in ax.get_xticklabels():
        label.set_rotation(78)
        label.set_fontsize(7)

    if weekly_context is not None:
        draw_weekly_context_panel(fig, gs, 1, weekly_context, "YM")
        fig.text(0.5, 0.02, "Time (America/New_York)", ha="center", fontsize=8)
    else:
        ax.set_xlabel("Time (America/New_York)")
    fig.savefig(out_path, dpi=135, bbox_inches="tight")
    plt.close(fig)


def render_charts(source_root: Path, output_root: Path, charts: int, force: bool) -> dict[str, object]:
    if output_root.exists() and force:
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)

    bars = read_bars(source_root / "states/ym_weekly_mid_ma500_bias/bars/YM_15m.csv")
    hourly_atr = hourly_with_atr(bars)
    units = read_units(source_root / "audits/ym_weekly_mid_ma500_bias/unit_fills.csv")
    if units.empty:
        (output_root / "INDEX.md").write_text("# YM PWC + 3xATR Weekly Charts\n\nNo trades.\n", encoding="utf-8")
        return {"charts": 0}

    weeks = []
    for week_start_str, trades in units.groupby("week_start"):
        week_start = pd.Timestamp(week_start_str, tz=NY)
        week_end = week_start + pd.Timedelta(days=7)
        week_15m = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        if week_15m.empty:
            continue
        prev = weekly_ohlc(bars, week_start - pd.Timedelta(days=7), week_start)
        if not prev:
            continue
        week_1h = to_hourly_with_ma(week_15m, "ma500")
        if week_1h.empty:
            continue
        prev_levels = {
            "prev_high": float(prev["high"]),
            "prev_low": float(prev["low"]),
            "prev_mid": float(prev["low"]) + 0.5 * (float(prev["high"]) - float(prev["low"])),
            "prev_close": float(prev["close"]),
        }
        score = abs(float(trades["net"].sum())) + len(trades) * 200.0
        weeks.append((score, week_start, week_15m, week_1h, trades.copy(), prev_levels, weekly_c3_info(bars, week_start)))

    chart_rows: list[dict[str, object]] = []
    weeks.sort(key=lambda item: item[0], reverse=True)
    for idx, (_score, week_start, week_15m, week_1h, trades, prev_levels, c3_info) in enumerate(weeks[:charts], start=1):
        rel = Path("charts") / ("%03d_%s.png" % (idx, week_start.date().isoformat()))
        net = float(trades["net"].sum())
        pwc = float(prev_levels["prev_close"])
        title = "YM weekly PWC + 3xATR(14) - %s - net $%.0f - %d trades" % (week_start.date().isoformat(), net, len(trades))
        weekly_context = compute_weekly_context(bars, week_start)
        plot_week_pwc_atr(
            output_root / rel,
            week_15m,
            week_1h,
            hourly_atr,
            week_start,
            prev_levels,
            trades,
            c3_info,
            title,
            weekly_context,
        )
        row = {
            "idx": idx,
            "week_start": week_start.date().isoformat(),
            "weekly_c3": "" if not c3_info else "%s_%s" % (c3_info["direction"], "hit" if c3_info["hit"] else "miss"),
            "pwc": pwc,
            "net": net,
            "trades": int(len(trades)),
            "chart": str(rel),
        }
        if weekly_context:
            row.update(
                {
                    "prev_doji": weekly_context["prev_doji"],
                    "weeks_since_ma10_cross": weekly_context["weeks_since_ma10_cross"],
                    "ma10_cross_direction": weekly_context["ma10_cross_direction"] or "",
                }
            )
        chart_rows.append(row)

    pd.DataFrame(chart_rows).to_csv(output_root / "chart_index.csv", index=False)
    lines = [
        "# YM Weekly PWC + 3xATR(14) Charts",
        "",
        "Full-week hourly candles with PWH/PWL/PW50/PWC, 15m MA500, and PWC ± 3× hourly ATR(14) bands. Broker-like MA500 strategy fills overlaid. Bottom panel: previous-week doji + 10W MA cross context.",
        "",
        "| # | Week | Weekly C3 | PWC | Net | Trades | Chart |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in chart_rows:
        lines.append(
            "| {idx} | {week_start} | {weekly_c3} | {pwc:.2f} | ${net:,.2f} | {trades} | [{chart}]({chart}) |".format(**row)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return {"charts": len(chart_rows), "index": output_root / "INDEX.md"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YM weekly charts with PWC and PWC ± 3xATR bands.")
    parser.add_argument(
        "--source-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts/ym_pwc_atr",
    )
    parser.add_argument("--charts", type=int, default=80)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    result = render_charts(args.source_root, args.output_root, args.charts, force=not args.no_force)
    print("Wrote %s (%d charts)" % (result.get("index", args.output_root / "INDEX.md"), int(result.get("charts", 0))), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
