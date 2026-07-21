"""Chart 100 winners + 100 losers from USDJPY Monday OR broker-like book.

Outputs::

    live/state/fx_monday_or_breakout_broker/charts_usdjpy/
      winners/
      losers/
      INDEX.md
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_monday_or_breakout_15m import resample_15m, week_bounds
from .fx_data import load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
DEFAULT_FILLS = (
    REPO
    / "live"
    / "state"
    / "fx_monday_or_breakout_broker"
    / "states"
    / "usdjpy_monday_or_breakout_shiftprim_htf"
    / "fills.csv"
)
DEFAULT_OUT = REPO / "live" / "state" / "fx_monday_or_breakout_broker" / "charts_usdjpy"
POINT_VALUE = 100_000.0
FEE = 1.50
JPY_USD = 110.0


def campaigns_from_fills(fills_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"] != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        entry_qty = float(entry["quantity"])
        entry_ts = entry["ts"]
        pnl = -FEE * entry_qty
        exit_qty = 0.0
        last_exit = exits.iloc[-1]
        for _, r in exits.iterrows():
            q = float(r["quantity"])
            px = float(r["price"])
            pts = (px - entry_px) * q if side == "long" else (entry_px - px) * q
            pnl += pts * POINT_VALUE - FEE * q
            exit_qty += q
        # Reconstruct R from first adverse exit geometry if possible; else from Mon OR later
        exit_reason = str(last_exit["reason"])
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": last_exit["ts"],
                "entry": entry_px,
                "exit": float(last_exit["price"]),
                "entry_qty": entry_qty,
                "pnl_jpy": float(pnl),
                "pnl_usd_approx": float(pnl) / JPY_USD,
                "result": "win" if pnl > 0 else "loss",
                "exit_reason": exit_reason,
            }
        )
    return pd.DataFrame(rows)


def attach_monday_or(trades: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    mon_h, mon_l, R, week_mon, stop, target = [], [], [], [], [], []
    for _, row in out.iterrows():
        entry_ts = pd.Timestamp(row["entry_ts"])
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize("UTC").tz_convert(NY)
        else:
            entry_ts = entry_ts.tz_convert(NY)
        mon0, _, _ = week_bounds(entry_ts)
        mon_bars = m15[(m15.index >= mon0) & (m15.index < mon0 + timedelta(days=1))]
        if mon_bars.empty:
            mh = ml = r = float("nan")
        else:
            mh = float(mon_bars["high"].max())
            ml = float(mon_bars["low"].min())
            r = mh - ml
        entry = float(row["entry"])
        if row["side"] == "long":
            st = entry - r
            tg = entry + 2.0 * r
        else:
            st = entry + r
            tg = entry - 2.0 * r
        mon_h.append(mh)
        mon_l.append(ml)
        R.append(r)
        week_mon.append(mon0.strftime("%Y-%m-%d"))
        stop.append(st)
        target.append(tg)
    out["monday_high"] = mon_h
    out["monday_low"] = mon_l
    out["R"] = R
    out["week_monday"] = week_mon
    out["stop"] = stop
    out["target"] = target
    return out


def plot_trade(m15: pd.DataFrame, row: pd.Series, out_path: Path, *, chart_idx: int) -> None:
    monday = pd.Timestamp(row["week_monday"])
    mon0, _, sat0 = week_bounds(NY_TZ.localize(datetime.combine(monday.date(), time(0, 0))))
    plot = m15[(m15.index >= mon0) & (m15.index < sat0)].copy()
    if plot.empty or not np.isfinite(row["R"]) or float(row["R"]) <= 0:
        return

    entry_ts = pd.Timestamp(row["entry_ts"])
    exit_ts = pd.Timestamp(row["exit_ts"])
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize("UTC").tz_convert(NY)
    else:
        entry_ts = entry_ts.tz_convert(NY)
    if exit_ts.tzinfo is None:
        exit_ts = exit_ts.tz_localize("UTC").tz_convert(NY)
    else:
        exit_ts = exit_ts.tz_convert(NY)

    side = str(row["side"])
    entry = float(row["entry"])
    exit_px = float(row["exit"])
    stop = float(row["stop"])
    target = float(row["target"])
    mon_h = float(row["monday_high"])
    mon_l = float(row["monday_low"])
    pnl_jpy = float(row["pnl_jpy"])
    pnl_usd = float(row["pnl_usd_approx"])
    result = str(row["result"])
    reason = str(row["exit_reason"])

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (15.0 / (24.0 * 60.0)) * 0.75
    axis_tz = plot.index.tz
    win_lo = float(min(plot["low"].min(), stop, target, mon_l, entry, exit_px))
    win_hi = float(max(plot["high"].max(), stop, target, mon_h, entry, exit_px))
    span = max(win_hi - win_lo, 1e-4)

    fig, ax = plt.subplots(figsize=(20, 7.5))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.45, alpha=0.85, zorder=3)
    min_body = max(span * 0.0008, 1e-5)
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

    ax.axhspan(mon_l, mon_h, color="#90caf9", alpha=0.18, zorder=1, label="Monday OR")
    ax.axhline(mon_h, color="#1565c0", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon high %.3f" % mon_h)
    ax.axhline(mon_l, color="#ef6c00", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon low %.3f" % mon_l)
    ax.axhline(stop, color="#c62828", linestyle=":", linewidth=1.4, alpha=0.95, label="Stop(1R) %.3f" % stop)
    ax.axhline(target, color="#6a1b9a", linestyle=":", linewidth=1.4, alpha=0.95, label="Target(2R) %.3f" % target)
    # DD cut levels
    if side == "long":
        dd30, dd50 = entry - 0.30 * float(row["R"]), entry - 0.50 * float(row["R"])
    else:
        dd30, dd50 = entry + 0.30 * float(row["R"]), entry + 0.50 * float(row["R"])
    ax.axhline(dd30, color="#ef9a9a", linestyle="-.", linewidth=0.9, alpha=0.8, label="DD30 %.3f" % dd30)
    ax.axhline(dd50, color="#e57373", linestyle="-.", linewidth=0.9, alpha=0.8, label="DD50 %.3f" % dd50)

    result_color = "#168a5a" if result == "win" else "#c43d3d"
    entry_x = mdates.date2num(entry_ts.to_pydatetime())
    exit_x = mdates.date2num(exit_ts.to_pydatetime())
    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.1, alpha=0.9)
    ax.axvline(exit_x, color=result_color, linewidth=1.1, linestyle="--", alpha=0.9)

    marker = "^" if side == "long" else "v"
    ax.scatter(
        [entry_x],
        [entry],
        marker=marker,
        s=110,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Entry %.3f" % entry,
    )
    ax.scatter(
        [exit_x],
        [exit_px],
        marker="X",
        s=95,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Exit %.3f (%s)" % (exit_px, reason),
    )

    pad = max(span * 0.06, 1e-4)
    ax.set_ylim(win_lo - pad, win_hi + pad)
    ax.set_title(
        "USDJPY Mon OR broker — #%03d %s %s | ¥%+.0f (≈$%+.0f) | %s → %s | R=%.3f"
        % (
            chart_idx,
            result.upper(),
            side,
            pnl_jpy,
            pnl_usd,
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%Y-%m-%d %H:%M"),
            float(row["R"]),
        ),
        fontsize=10,
    )
    ax.set_ylabel("USDJPY")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.5, alpha=0.7)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=axis_tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d", tz=axis_tz))
    ax.set_xlabel("Mon–Fri week of %s (America/New_York)" % mon0.strftime("%Y-%m-%d"))
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=125, bbox_inches="tight")
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fills", type=Path, default=DEFAULT_FILLS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--wins", type=int, default=100)
    parser.add_argument("--losses", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args(list(argv) if argv is not None else None)

    print("Building campaigns from fills...", flush=True)
    trades = campaigns_from_fills(args.fills)
    print(
        "  %d campaigns (%d wins / %d losses)"
        % (len(trades), (trades["result"] == "win").sum(), (trades["result"] == "loss").sum()),
        flush=True,
    )

    one_m = REPO / "fx" / "usdjpy_1m.csv"
    print("Loading USDJPY 15m...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, "USDJPY")
    m15 = resample_15m(concat_all_1m(bars_by_day))
    if m15.index.tz is None:
        m15.index = m15.index.tz_localize(NY)
    else:
        m15.index = m15.index.tz_convert(NY)

    trades = attach_monday_or(trades, m15)
    trades = trades[np.isfinite(trades["R"]) & (trades["R"] > 0)].copy()

    rng = random.Random(args.seed)
    win_idx = trades.index[trades["result"] == "win"].tolist()
    loss_idx = trades.index[trades["result"] == "loss"].tolist()
    n_w = min(args.wins, len(win_idx))
    n_l = min(args.losses, len(loss_idx))
    win_pick = rng.sample(win_idx, n_w)
    loss_pick = rng.sample(loss_idx, n_l)

    winners_dir = args.output_root / "winners"
    losers_dir = args.output_root / "losers"
    for d in (winners_dir, losers_dir):
        if d.exists():
            for p in d.glob("*.png"):
                p.unlink()
        d.mkdir(parents=True, exist_ok=True)

    rows_meta: List[dict] = []

    def _write(picked, folder: Path, label: str) -> None:
        for i, ti in enumerate(picked, start=1):
            row = trades.loc[ti]
            stamp = pd.Timestamp(row["entry_ts"]).tz_convert(NY).strftime("%Y-%m-%d_%H%M")
            fname = "%03d_%s_%s_%s.png" % (i, row["result"], row["side"], stamp)
            out = folder / fname
            plot_trade(m15, row, out, chart_idx=i)
            rows_meta.append(
                {
                    "folder": label,
                    "idx": i,
                    "result": row["result"],
                    "side": row["side"],
                    "entry": str(row["entry_ts"]),
                    "exit": str(row["exit_ts"]),
                    "pnl_jpy": float(row["pnl_jpy"]),
                    "pnl_usd": float(row["pnl_usd_approx"]),
                    "reason": row["exit_reason"],
                    "path": "%s/%s" % (label, fname),
                }
            )
            if i % 25 == 0:
                print("  %s %d/%d" % (label, i, len(picked)), flush=True)

    print("Charting %d winners..." % n_w, flush=True)
    _write(win_pick, winners_dir, "winners")
    print("Charting %d losers..." % n_l, flush=True)
    _write(loss_pick, losers_dir, "losers")

    lines = [
        "# USDJPY Monday OR — broker-like trade charts",
        "",
        "Random sample of **%d winners** + **%d losers** (seed `%d`) from "
        "`usdjpy_monday_or_breakout_shiftprim_htf`."
        % (n_w, n_l, args.seed),
        "",
        "- [`winners/`](winners/) — %d PNGs" % n_w,
        "- [`losers/`](losers/) — %d PNGs" % n_l,
        "",
        "Each chart = Mon–Fri week, 15m candles, Monday OR, DD30/DD50, stop(1R), target(2R).",
        "P&L in JPY (≈USD @ 110).",
        "",
        "| Folder | # | Side | Entry | Exit | ¥ P/L | ≈$ | Reason | Chart |",
        "|---|---:|---|---|---|---:|---:|---|---|",
    ]
    for r in rows_meta:
        lines.append(
            "| %s | %d | %s | %s | %s | %+.0f | %+.0f | %s | [%s](%s) |"
            % (
                r["folder"],
                r["idx"],
                r["side"],
                str(r["entry"])[:16],
                str(r["exit"])[:16],
                r["pnl_jpy"],
                r["pnl_usd"],
                r["reason"],
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d charts → %s" % (len(rows_meta), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
