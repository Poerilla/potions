"""Chart 100 winners + 100 losers from XAUUSD Monday OR broker-like book.

Best metals Monday OR tag: ``M2_S2_R3`` (Phase 2 extended / heat caution).

Outputs::

    live/state/monday_or_sizing_sweep_broker_xauusd/charts_m2_s2_r3/
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
    / "monday_or_sizing_sweep_broker_xauusd"
    / "audits"
    / "xauusd_m2_s2_r3"
    / "xauusd_m2_s2_r3"
    / "unit_fills.csv"
)
DEFAULT_OUT = (
    REPO / "live" / "state" / "monday_or_sizing_sweep_broker_xauusd" / "charts_m2_s2_r3"
)
FEE = 1.50  # informational; campaign PnL comes from unit_fills.usd


def campaigns_from_unit_fills(fills_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["entry_ts"] = pd.to_datetime(fills["entry_ts"], utc=True)
    fills["exit_ts"] = pd.to_datetime(fills["exit_ts"], utc=True)
    fills["entry_price"] = pd.to_numeric(fills["entry_price"], errors="coerce")
    fills["exit_price"] = pd.to_numeric(fills["exit_price"], errors="coerce")
    fills["usd"] = pd.to_numeric(fills["usd"], errors="coerce").fillna(0.0)
    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values(["entry_ts", "unit_id"])
        first = g.iloc[0]
        last = g.sort_values("exit_ts").iloc[-1]
        side = "long" if str(first["direction"]).lower().startswith("long") else "short"
        pnl = float(g["usd"].sum())
        # Prefer a decisive exit reason when present
        reasons = g["exit_reason"].astype(str).tolist()
        for prefer in ("stop", "target", "dd50", "dd30", "week_end"):
            if prefer in reasons:
                exit_reason = prefer
                break
        else:
            exit_reason = str(last["exit_reason"])
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": first["entry_ts"],
                "exit_ts": last["exit_ts"],
                "entry": float(first["entry_price"]),
                "exit": float(last["exit_price"]),
                "entry_qty": float(len(g)),
                "pnl_usd": pnl,
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
    pnl_usd = float(row["pnl_usd"])
    result = str(row["result"])
    reason = str(row["exit_reason"])
    r = float(row["R"])

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
    ax.axhline(mon_h, color="#1565c0", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon high %.2f" % mon_h)
    ax.axhline(mon_l, color="#ef6c00", linestyle="--", linewidth=1.3, alpha=0.95, label="Mon low %.2f" % mon_l)
    ax.axhline(stop, color="#c62828", linestyle=":", linewidth=1.4, alpha=0.95, label="Stop(1R) %.2f" % stop)
    ax.axhline(target, color="#6a1b9a", linestyle=":", linewidth=1.4, alpha=0.95, label="Target(2R) %.2f" % target)
    if side == "long":
        dd30, dd50 = entry - 0.30 * r, entry - 0.50 * r
    else:
        dd30, dd50 = entry + 0.30 * r, entry + 0.50 * r
    ax.axhline(dd30, color="#ef9a9a", linestyle="-.", linewidth=0.9, alpha=0.8, label="DD30 %.2f" % dd30)
    ax.axhline(dd50, color="#e57373", linestyle="-.", linewidth=0.9, alpha=0.8, label="DD50 %.2f" % dd50)

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
        label="Entry %.2f" % entry,
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
        label="Exit %.2f (%s)" % (exit_px, reason),
    )

    pad = max(span * 0.06, 1e-4)
    ax.set_ylim(win_lo - pad, win_hi + pad)
    ax.set_title(
        "XAUUSD Mon OR M2_S2_R3 — #%03d %s %s | $%+.0f | %s → %s | R=%.2f | qty=%d"
        % (
            chart_idx,
            result.upper(),
            side,
            pnl_usd,
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%Y-%m-%d %H:%M"),
            r,
            int(row["entry_qty"]),
        ),
        fontsize=10,
    )
    ax.set_ylabel("XAUUSD")
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
    parser.add_argument("--seed", type=int, default=20260721)
    args = parser.parse_args(list(argv) if argv is not None else None)

    print("Building campaigns from unit fills...", flush=True)
    trades = campaigns_from_unit_fills(args.fills)
    print(
        "  %d campaigns (%d wins / %d losses)"
        % (len(trades), (trades["result"] == "win").sum(), (trades["result"] == "loss").sum()),
        flush=True,
    )

    one_m = REPO / "fx" / "xauusd_1m.csv"
    print("Loading XAUUSD 15m...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, "XAUUSD")
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
                    "pnl_usd": float(row["pnl_usd"]),
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
        "# XAUUSD Monday OR — broker-like trade charts (`M2_S2_R3`)",
        "",
        "Best metals Monday OR tag from the broker sizing sweep "
        "(XAGUSD excluded — all tags negative). "
        "Random sample of **%d winners** + **%d losers** (seed `%d`) from "
        "`xauusd_m2_s2_r3` unit fills."
        % (n_w, n_l, args.seed),
        "",
        "- [`winners/`](winners/) — %d PNGs" % n_w,
        "- [`losers/`](losers/) — %d PNGs" % n_l,
        "",
        "Each chart = Mon–Fri week, 15m candles, Monday OR, DD30/DD50, stop(1R), target(2R).",
        "Campaign P&L from unit fills (USD, $1.50/unit fees already netted).",
        "",
        "| Folder | # | Side | Entry | Exit | $ P/L | Reason | Chart |",
        "|---|---:|---|---|---|---:|---|---|",
    ]
    for r in rows_meta:
        lines.append(
            "| %s | %d | %s | %s | %s | %+.0f | %s | [%s](%s) |"
            % (
                r["folder"],
                r["idx"],
                r["side"],
                str(r["entry"])[:16],
                str(r["exit"])[:16],
                r["pnl_usd"],
                r["reason"],
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    wrote = len(list(winners_dir.glob("*.png"))) + len(list(losers_dir.glob("*.png")))
    print("Wrote %d charts → %s" % (wrote, args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
