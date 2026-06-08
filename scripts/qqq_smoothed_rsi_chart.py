#!/usr/bin/env python3
"""QQQ smoothed RSI chart."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_smoothed_rsi_chart"
DEFAULT_START = "2000-01-01"


def compute_rsi(daily: pd.DataFrame, length: int, smooth: int) -> pd.DataFrame:
    out = daily.copy().sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(out["close"], errors="coerce")
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1.0 / float(length), adjust=False, min_periods=length).mean()
    avg_loss = losses.ewm(alpha=1.0 / float(length), adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out["rsi"] = 100.0 - (100.0 / (1.0 + rs))
    out.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "rsi"] = 100.0
    out.loc[(avg_loss == 0.0) & (avg_gain == 0.0), "rsi"] = 50.0
    out["rsi_smooth"] = out["rsi"].ewm(span=smooth, adjust=False, min_periods=smooth).mean()
    out["sma50"] = close.rolling(50, min_periods=20).mean()
    out["sma200"] = close.rolling(200, min_periods=80).mean()
    return out


def plot_chart(daily: pd.DataFrame, out_path: Path, rsi_len: int, smooth: int, last_bars: int | None) -> None:
    work = daily.copy().sort_values("date").reset_index(drop=True)
    if last_bars is not None:
        work = work.tail(last_bars).copy().reset_index(drop=True)

    fig, (ax_price, ax_rsi) = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        sharex=True,
        height_ratios=[2.1, 1.2],
    )
    ax_price.plot(work["date"], work["close"], color="#111827", linewidth=1.25, label="QQQ adjusted close")
    ax_price.plot(work["date"], work["sma50"], color="#2563eb", linewidth=1.0, label="SMA50")
    ax_price.plot(work["date"], work["sma200"], color="#f97316", linewidth=1.0, label="SMA200")
    ax_price.set_ylabel("Adjusted price")
    ax_price.grid(True, alpha=0.25)
    ax_price.legend(loc="upper left", fontsize=8)
    span = "recent %d bars" % last_bars if last_bars else "full history"
    ax_price.set_title("QQQ smoothed RSI (%s)" % span)

    ax_rsi.axhspan(70, 100, color="#fecaca", alpha=0.22)
    ax_rsi.axhspan(0, 30, color="#bfdbfe", alpha=0.25)
    ax_rsi.axhline(70, color="#dc2626", linewidth=0.8, linestyle="--")
    ax_rsi.axhline(50, color="#6b7280", linewidth=0.8, linestyle=":")
    ax_rsi.axhline(30, color="#2563eb", linewidth=0.8, linestyle="--")
    ax_rsi.plot(work["date"], work["rsi"], color="#94a3b8", linewidth=0.9, alpha=0.85, label="RSI%d" % rsi_len)
    ax_rsi.plot(work["date"], work["rsi_smooth"], color="#7c3aed", linewidth=1.6, label="RSI%d EMA%d" % (rsi_len, smooth))
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel("RSI")
    ax_rsi.grid(True, alpha=0.25)
    ax_rsi.legend(loc="upper left", fontsize=8)
    ax_rsi.xaxis.set_major_locator(mdates.YearLocator(base=1 if last_bars else 2))
    ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_report(out_dir: Path, daily: pd.DataFrame, start: str, end: str, rsi_len: int, smooth: int) -> None:
    latest = daily.dropna(subset=["rsi", "rsi_smooth"]).iloc[-1]
    state = "overbought" if latest["rsi_smooth"] >= 70 else "oversold" if latest["rsi_smooth"] <= 30 else "neutral"
    lines = [
        "# QQQ Smoothed RSI Chart",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (start, end),
        "",
        "Indicator:",
        "",
        "- RSI uses Wilder-style RSI(%d)." % rsi_len,
        "- Smoothed RSI is EMA(%d) of RSI(%d)." % (smooth, rsi_len),
        "- Overbought/oversold reference bands are 70 / 30.",
        "",
        "Latest completed row: **%s**." % pd.Timestamp(latest["date"]).date().isoformat(),
        "",
        "| Close | RSI%d | Smoothed RSI | State |" % rsi_len,
        "|---:|---:|---:|---|",
        "| %.2f | %.2f | %.2f | %s |" % (
            float(latest["close"]),
            float(latest["rsi"]),
            float(latest["rsi_smooth"]),
            state,
        ),
        "",
        "## Charts",
        "",
        "- Full history: [`charts/qqq_smoothed_rsi_full.png`](charts/qqq_smoothed_rsi_full.png)",
        "- Recent zoom: [`charts/qqq_smoothed_rsi_recent.png`](charts/qqq_smoothed_rsi_recent.png)",
        "",
        "## Files",
        "",
        "- `QQQ_smoothed_rsi_daily.csv`",
    ]
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QQQ smoothed RSI charts.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--rsi-len", type=int, default=14)
    parser.add_argument("--smooth", type=int, default=14)
    parser.add_argument("--recent-bars", type=int, default=760)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = compute_rsi(daily, args.rsi_len, args.smooth)
    daily.to_csv(out_dir / "QQQ_smoothed_rsi_daily.csv", index=False)
    plot_chart(daily, out_dir / "charts" / "qqq_smoothed_rsi_full.png", args.rsi_len, args.smooth, last_bars=None)
    plot_chart(daily, out_dir / "charts" / "qqq_smoothed_rsi_recent.png", args.rsi_len, args.smooth, last_bars=args.recent_bars)
    write_report(out_dir, daily, args.start, args.end, args.rsi_len, args.smooth)
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
