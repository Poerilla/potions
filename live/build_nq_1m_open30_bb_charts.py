"""NQ RTH first 30 minutes (09:30–09:59) on 1m candles + 9:30 open + Bollinger bands."""

from __future__ import annotations

import argparse
import html
import random
import shutil
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .notify_email import send_email
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
RTH_OPEN = time(9, 30)
OPEN30_END = time(10, 0)  # exclusive — 09:30..09:59 (30 bars)
BB_LEN = 20
BB_STD = 2.0
DEFAULT_OUT = REPO / "live" / "state" / "nq_1m_open30_bb_charts"


def bollinger(close: pd.Series, length: int = BB_LEN, n_std: float = BB_STD) -> pd.DataFrame:
    mid = close.rolling(length, min_periods=length).mean()
    std = close.rolling(length, min_periods=length).std()
    return pd.DataFrame({"bb_mid": mid, "bb_upper": mid + n_std * std, "bb_lower": mid - n_std * std})


def plot_candles(ax, df: pd.DataFrame, width_days: float) -> None:
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.75, alpha=0.9, zorder=3)
    span = float(df["high"].max() - df["low"].min()) if len(df) else 0.0
    min_body = max(span * 0.0008, 0.01)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, min(o, c)),
                width_days,
                max(abs(c - o), min_body),
                facecolor=color,
                edgecolor=color,
                linewidth=0.35,
                alpha=0.82,
                zorder=4,
            )
        )


def open30_slice(rth: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(datetime.combine(rth.index[0].date(), RTH_OPEN), tz=NY)
    end = pd.Timestamp(datetime.combine(rth.index[0].date(), OPEN30_END), tz=NY)
    return rth[(rth.index >= start) & (rth.index < end)].copy()


def rth_open_price(open30: pd.DataFrame) -> tuple[pd.Timestamp, float] | None:
    if open30.empty:
        return None
    row = open30.iloc[0]
    return pd.Timestamp(open30.index[0]), float(row["open"])


def build_charts(
    *,
    output_root: Path,
    sample_size: int,
    seed: int,
    force: bool,
    email: bool,
) -> list[dict[str, object]]:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    cfg = MARKETS["nq"]
    print("Loading NQ 1m bars...", flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    rng = random.Random(seed)
    candidate_days = sorted(day for day, df in by_day.items() if df is not None and not df.empty)
    rng.shuffle(candidate_days)

    selected: list[date] = []
    open30_by_day: dict[date, pd.DataFrame] = {}
    for day in candidate_days:
        rth = _rth_bars(by_day.get(day), day)
        open30 = open30_slice(rth)
        if len(open30) < 30 or rth_open_price(open30) is None:
            continue
        selected.append(day)
        open30_by_day[day] = open30
        if len(selected) >= sample_size:
            break
    selected = sorted(selected)

    rows: list[dict[str, object]] = []
    width_days = (1.0 / (24.0 * 60.0)) * 0.72
    for idx, day in enumerate(selected, start=1):
        open30 = open30_by_day[day]
        marker = rth_open_price(open30)
        if marker is None:
            continue
        marker_ts, marker_open = marker
        bb = bollinger(open30["close"])
        plot_df = open30.join(bb)

        fig, ax = plt.subplots(figsize=(16, 7))
        plot_candles(ax, plot_df, width_days=width_days)
        ax.plot(plot_df.index, plot_df["bb_mid"], color="#1565c0", linewidth=1.2, label="BB mid (%d)" % BB_LEN, zorder=5)
        ax.plot(
            plot_df.index,
            plot_df["bb_upper"],
            color="#6a1b9a",
            linewidth=1.0,
            linestyle="--",
            label="BB upper",
            zorder=5,
        )
        ax.plot(
            plot_df.index,
            plot_df["bb_lower"],
            color="#6a1b9a",
            linewidth=1.0,
            linestyle="--",
            label="BB lower",
            zorder=5,
        )
        ax.fill_between(plot_df.index, plot_df["bb_lower"], plot_df["bb_upper"], color="#6a1b9a", alpha=0.06, zorder=1)
        ax.axhline(marker_open, color="#0057b8", linewidth=1.35, linestyle="-", alpha=0.9, label="09:30 open %.2f" % marker_open)
        ax.axvline(marker_ts, color="#0057b8", linewidth=1.0, linestyle=":", alpha=0.55)
        ax.annotate(
            "09:30 open %.2f" % marker_open,
            xy=(marker_ts, marker_open),
            xytext=(8, 14),
            textcoords="offset points",
            color="#0057b8",
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": "#0057b8", "lw": 0.9},
        )
        ax.set_title(
            "NQ first 30 min (1m) %s  |  09:30 open + Bollinger(%d, %.1fσ)"
            % (day.isoformat(), BB_LEN, BB_STD)
        )
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e2e2e2", linewidth=0.55, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55], tz=plot_df.index.tz))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=plot_df.index.tz))
        ax.set_xlabel("Time (America/New_York)")
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")
            label.set_fontsize(8)
        ax.set_xlim(plot_df.index[0] - timedelta(seconds=30), plot_df.index[-1] + timedelta(seconds=30))

        rel = Path("charts") / ("%02d_%s.png" % (idx, day.isoformat()))
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": day.isoformat(),
                "open_930": marker_open,
                "close_959": float(open30.iloc[-1]["close"]),
                "range_pts": float(open30["high"].max() - open30["low"].min()),
                "chart": str(rel),
            }
        )
        print("  chart %02d/%d  %s" % (idx, len(selected), day.isoformat()), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# NQ 1m — first 30 minutes + 09:30 open + Bollinger bands",
        "",
        "**%d** NY RTH sessions (seed `%d`). Window **09:30–09:59** ET on 1-minute candles." % (len(rows), seed),
        "Blue line = **09:30 opening price**. Only indicator = Bollinger(%d, %.1fσ)." % (BB_LEN, BB_STD),
        "",
        "| # | Session | 09:30 Open | 09:59 Close | Range | Chart |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {session} | {open_930:.2f} | {close_959:.2f} | {range_pts:.1f} | [{chart}]({chart}) |".format(
                **row
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = output_root / "open30_bb_charts.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(output_root / "INDEX.md", arcname="INDEX.md")
        zf.write(output_root / "chart_manifest.csv", arcname="chart_manifest.csv")
        for row in rows:
            zf.write(output_root / row["chart"], arcname=str(row["chart"]))

    text = "\n".join(
        [
            "potions: NQ first-30min 1m charts (09:30 open + Bollinger)",
            "",
            "Hub: %s" % output_root,
            "Sessions: %d (seed %d)" % (len(rows), seed),
            "Window: NY RTH 09:30–09:59 on 1-minute candles.",
            "Indicator: Bollinger(%d, %.1fσ) only; blue line = 09:30 open." % (BB_LEN, BB_STD),
            "",
            "Zip: %s" % zip_path,
            "",
            "Sessions charted:",
        ]
        + ["  %02d  %s  open=%.2f" % (r["idx"], r["session"], r["open_930"]) for r in rows]
    )
    html_rows = "\n".join(
        "<tr><td>%d</td><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.1f</td></tr>"
        % (r["idx"], html.escape(str(r["session"])), r["open_930"], r["close_959"], r["range_pts"])
        for r in rows
    )
    html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>NQ first 30 minutes — 1m + 09:30 open + Bollinger</h2>
<p>%d sessions (seed %d). Window <strong>09:30–09:59</strong> ET. Hub <code>%s</code>.</p>
<p>Zip attached when under size limit.</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>#</th><th>Session</th><th>09:30 open</th><th>09:59 close</th><th>Range</th></tr>
%s
</table></body></html>""" % (len(rows), seed, html.escape(str(output_root)), html_rows)
    (output_root / "EMAIL.txt").write_text(text + "\n", encoding="utf-8")
    (output_root / "EMAIL.html").write_text(html_body, encoding="utf-8")

    if email:
        atts = [zip_path] if zip_path.exists() and zip_path.stat().st_size < 7.5 * 1024 * 1024 else []
        send_email(
            subject="potions: NQ first-30min 1m charts (09:30 open + BB)",
            body=text,
            html=html_body,
            attachments=atts or None,
        )
        print("email sent (attachments=%d)" % len(atts), flush=True)

    print("Wrote %d charts → %s" % (len(rows), output_root), flush=True)
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sample-size", type=int, default=15)
    ap.add_argument("--seed", type=int, default=1930)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)
    build_charts(
        output_root=args.output_root,
        sample_size=args.sample_size,
        seed=args.seed,
        force=args.force,
        email=args.email,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
