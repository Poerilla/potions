"""Chart even-timeline sample of EURUSD 15m ST DCA broker-like trades."""

from __future__ import annotations

import argparse
import shutil
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .eurusd_intraday_ma_st_research import compute_supertrend_fast
from .eurusd_intraday_st_dca_replay import STRATEGY_ID, _resample_15m
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
POINT_VALUE = 50_000.0  # half-lot unit
FEE = 0.75
EXIT_REASONS = {
    "stop",
    "protective_stop",
    "session_end",
    "st_flip",
    "close",
    "target",
    "trail_close",
    "thesis_end",
}


def _load_campaigns(fills_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"].isin(["entry", "add"])]
        exits = g[g["reason"].isin(EXIT_REASONS)]
        if entries.empty or exits.empty:
            continue
        # Weighted entry
        qty = float(entries["quantity"].sum())
        entry_px = float((entries["price"] * entries["quantity"]).sum() / qty)
        entry_ts = pd.Timestamp(entries.iloc[0]["ts"])
        exit_row = exits.iloc[-1]
        exit_px = float(exit_row["price"])
        exit_ts = pd.Timestamp(exit_row["ts"])
        side = "long" if str(entries.iloc[0]["side"]).lower() == "buy" else "short"
        if side == "long":
            pts = (exit_px - entry_px) * qty
        else:
            pts = (entry_px - exit_px) * qty
        usd = pts * POINT_VALUE - FEE * qty
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "entry": entry_px,
                "exit": exit_px,
                "qty": qty,
                "pnl_usd": usd,
                "result": "win" if usd > 0 else "loss",
                "exit_reason": str(exit_row["reason"]),
                "n_fills_entry": int(len(entries)),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def even_sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.copy()
    idxs = np.linspace(0, len(df) - 1, n)
    idxs = np.unique(np.rint(idxs).astype(int))
    # pad if unique collapsed
    while len(idxs) < n:
        extra = sorted(set(range(len(df))) - set(idxs))
        if not extra:
            break
        idxs = np.sort(np.append(idxs, extra[: n - len(idxs)]))
    return df.iloc[idxs].reset_index(drop=True)


def plot_trade(m15: pd.DataFrame, row: pd.Series, out_path: Path, idx: int) -> None:
    pad = timedelta(hours=6)
    plot = m15[(m15.index >= row.entry_ts - pad) & (m15.index <= row.exit_ts + pad)].copy()
    if plot.empty:
        return
    x = mdates.date2num(plot.index.to_pydatetime())
    width = (15.0 / (24.0 * 60.0)) * 0.75
    result_color = "#168a5a" if row.result == "win" else "#c43d3d"
    entry_x = mdates.date2num(pd.Timestamp(row.entry_ts).to_pydatetime())
    exit_x = mdates.date2num(pd.Timestamp(row.exit_ts).to_pydatetime())

    fig, ax = plt.subplots(figsize=(16, 7))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.8, zorder=3)
    span = float(plot["high"].max() - plot["low"].min())
    min_body = max(span * 0.001, 1e-6)
    for xi, o, c, col in zip(x, plot["open"], plot["close"], colors):
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2, min(o, c)),
                width,
                max(abs(c - o), min_body),
                facecolor=col,
                edgecolor=col,
                linewidth=0.3,
                alpha=0.85,
                zorder=4,
            )
        )
    if "supertrend" in plot.columns:
        bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
        bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
        ax.plot(plot.index, bull, color="#009c5b", linewidth=1.8, label="15m ST bull", zorder=6)
        ax.plot(plot.index, bear, color="#d62728", linewidth=1.8, label="15m ST bear", zorder=6)

    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.1)
    ax.axvline(exit_x, color=result_color, linewidth=1.1, linestyle="--")
    marker = "^" if row.side == "long" else "v"
    ax.scatter([entry_x], [row.entry], marker=marker, s=110, color=result_color, edgecolors="white", zorder=8)
    ax.scatter([exit_x], [row.exit], marker="X", s=90, color=result_color, edgecolors="white", zorder=8)

    ax.set_title(
        "EURUSD 15m ST DCA #%03d %s %s | qty %.1f | $%+.0f | %s → %s | %s"
        % (
            idx,
            row.result.upper(),
            row.side,
            row.qty,
            row.pnl_usd,
            pd.Timestamp(row.entry_ts).strftime("%Y-%m-%d %H:%M"),
            pd.Timestamp(row.exit_ts).strftime("%Y-%m-%d %H:%M"),
            row.exit_reason,
        ),
        fontsize=10,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=plot.index.tz))
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Chart EURUSD 15m ST DCA trades")
    parser.add_argument(
        "--replay-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_intraday_st_dca_broker",
    )
    parser.add_argument("--strategy-id", default=STRATEGY_ID)
    parser.add_argument("--title", default="EURUSD 15m ST DCA")
    parser.add_argument("--max-charts", type=int, default=300)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    args = parser.parse_args(argv)

    fills = args.replay_root / "states" / args.strategy_id / "fills.csv"
    out = args.replay_root / "charts"
    if args.force and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    campaigns = _load_campaigns(fills)
    print("Campaigns:", len(campaigns), flush=True)
    picked = even_sample(campaigns, args.max_charts)
    print("Charting %d / %d (even timeline sample)" % (len(picked), len(campaigns)), flush=True)

    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    print("Loading 15m for overlays...", flush=True)
    gby = load_fx_1m_by_ny_date(one_m_path, "EURUSD")
    one_m = concat_all_1m(gby).sort_index()
    one_m = one_m[
        (one_m.index >= pd.Timestamp(args.start, tz=NY))
        & (one_m.index <= pd.Timestamp(args.end, tz=NY))
    ]
    m15 = compute_supertrend_fast(_resample_15m(one_m), atr_len=14, multiplier=3.0)

    lines = [
        "# %s — trade charts" % args.title,
        "",
        "Even sample of **%d** campaigns from **%d** total (timeline-spaced)."
        % (len(picked), len(campaigns)),
        "15m candles + ATR SuperTrend 14×3, entry/exit markers, DCA qty in title.",
        "",
        "| # | Result | Side | Qty | Entry | Exit | P/L | Chart |",
        "|---:|---|---|---:|---|---|---:|---|",
    ]
    for i, r in enumerate(picked.itertuples(index=False), start=1):
        stamp = pd.Timestamp(r.entry_ts).strftime("%Y-%m-%d_%H%M")
        fname = "%03d_%s_%s.png" % (i, r.result, stamp)
        path = out / fname
        plot_trade(m15, picked.iloc[i - 1], path, i)
        lines.append(
            "| %d | %s | %s | %.1f | %s | %s | $%+.0f | [%s](%s) |"
            % (
                i,
                r.result,
                r.side,
                r.qty,
                pd.Timestamp(r.entry_ts).strftime("%Y-%m-%d %H:%M"),
                pd.Timestamp(r.exit_ts).strftime("%Y-%m-%d %H:%M"),
                r.pnl_usd,
                fname,
                fname,
            )
        )
        if i % 25 == 0:
            print("  %d/%d" % (i, len(picked)), flush=True)
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Also copy index one level up
    (args.replay_root / "CHARTS.md").write_text(
        "# Charts\n\nSee [charts/INDEX.md](charts/INDEX.md).\n",
        encoding="utf-8",
    )
    print("Wrote", out / "INDEX.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
