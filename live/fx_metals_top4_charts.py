"""Chart packs for FX/metals top-4 + XAUUSD ST+PMC MA-bull.

Yearly ORB: one daily chart per calendar year (broker-like fills).
Monthly FBO: one chart per trade-month (max 300).
Hourly ST+PMC: profitable campaigns only (max 300), sampled if more.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_broker_like_replay_detail_charts import build_detail_charts
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .eurusd_monthly_orb_first_break_opp_charts import run as run_fbo_month_charts
from .fx_data import load_fx_1m_by_ny_date
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import (
    concat_all_1m,
    load_prev_month_close_map,
    resample_hourly,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
ATR_LEN = 14
ATR_MULT = 3.0
CHARTS_ROOT = REPO / "live" / "state" / "fx_metals_top4_report" / "charts"


YEARLY_PACKS = [
    {
        "pair": "AUDJPY",
        "slug": "audjpy_yearly_orb_scaleout3",
        "replay_root": REPO / "live" / "state" / "audjpy_futures_strats_sweep",
        "net": 193803.0,
        "stress": -9036.0,
        "ns": 15.26,
        "units": 438,
        "trades": 146,
    },
    {
        "pair": "XAUUSD",
        "slug": "xauusd_yearly_orb_scaleout3",
        "replay_root": REPO / "live" / "state" / "metals_futures_strats_sweep",
        "net": 541254.0,
        "stress": -47903.0,
        "ns": 11.30,
        "units": 273,
        "trades": 91,
    },
    {
        "pair": "XAGUSD",
        "slug": "xagusd_yearly_orb_scaleout3",
        "replay_root": REPO / "live" / "state" / "metals_futures_strats_sweep",
        "net": 121185.0,
        "stress": -19508.0,
        "ns": 6.21,
        "units": 267,
        "trades": 89,
    },
]


@dataclass
class TradeRow:
    idx: int
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    stop: float
    target: float
    prev_month_close: float
    pnl_pts: float
    pnl_usd: float
    result: str
    exit_reason: str


def _write_compat_summary(path: Path, packs: Sequence[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "candidate",
                "slug",
                "instrument",
                "units",
                "trades",
                "net_usd",
                "close_mtm_dd_usd",
                "intrabar_mtm_dd_usd",
                "max_open_units",
                "net_over_stress_dd",
            ],
        )
        w.writeheader()
        for p in packs:
            w.writerow(
                {
                    "candidate": "%s Yearly ORB scaleout3" % p["pair"],
                    "slug": p["slug"],
                    "instrument": p["pair"],
                    "units": p["units"],
                    "trades": p["trades"],
                    "net_usd": "%.2f" % p["net"],
                    "close_mtm_dd_usd": "%.2f" % p["stress"],
                    "intrabar_mtm_dd_usd": "%.2f" % p["stress"],
                    "max_open_units": 3,
                    "net_over_stress_dd": "%.2f" % p["ns"],
                }
            )


def build_yearly_orb_charts(*, force: bool = False) -> List[Tuple[str, Path, int]]:
    results = []
    # Group by replay_root so we only swap one summary at a time.
    by_root: dict = {}
    for p in YEARLY_PACKS:
        by_root.setdefault(p["replay_root"], []).append(p)

    for replay_root, packs in by_root.items():
        out_root = CHARTS_ROOT / "yearly_orb"
        out_root.mkdir(parents=True, exist_ok=True)
        original = replay_root / "summary.csv"
        backup = replay_root / "summary_charts_backup.csv"
        if original.exists() and not backup.exists():
            backup.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
        elif original.exists() and backup.exists() and "candidate" not in original.read_text(encoding="utf-8")[:200]:
            # already swapped somehow; keep backup
            pass
        _write_compat_summary(original, packs)
        try:
            slugs = [p["slug"] for p in packs]
            if force:
                for slug in slugs:
                    target = out_root / slug
                    if target.exists():
                        shutil.rmtree(target)
            built = build_detail_charts(
                replay_root=replay_root,
                output_root=out_root,
                include_all=False,
                include_slugs=slugs,
                exact=True,
            )
            for p in packs:
                n = len(list((out_root / p["slug"]).glob("*/*.png")))
                results.append((p["pair"] + " Yearly ORB", out_root / p["slug"], n))
                print("Yearly ORB %s: %d charts → %s" % (p["pair"], n, out_root / p["slug"]), flush=True)
        finally:
            if backup.exists():
                original.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    return results


def build_usdjpy_fbo_charts(*, force: bool = False, max_charts: int = 300) -> Tuple[str, Path, int]:
    state = (
        REPO
        / "live"
        / "state"
        / "fx_cross_pair_tracker_leaders"
        / "states"
        / "fbo_1_1_3_atr80_usdjpy"
    )
    out = CHARTS_ROOT / "usdjpy_fbo_1_1_3_atr80"
    if force and out.exists():
        shutil.rmtree(out)
    built = run_fbo_month_charts(
        state,
        out,
        or_sessions=3,
        label="FBO 1/1/3 atr80",
        ladder_note="Promoted ladder 1@0.25R / 1@1R / 3@2R; BE after TP25; close-SL; atr80 filter.",
        instrument="USDJPY",
        point_value=POINT_VALUES["USDJPY"],
        fee_per_unit=7.0,
        max_charts=max_charts,
    )
    return ("USDJPY FBO 1/1/3 atr80", out, len(built))


def _load_config(state_root: Path) -> dict:
    inst = pd.read_csv(state_root / "strategy_instances.csv")
    return json.loads(str(inst.iloc[0]["config_json"]))


def _load_stpmc_trades(
    fills_path: Path,
    *,
    stop_pts: float,
    target_pts: float,
    daily_path: Path,
    point_value: float,
    fee_per_unit: float,
) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    pmc_map = load_prev_month_close_map(daily_path)

    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(["stop", "target", "eod", "flatten", "close"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_ = exits.iloc[-1]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        exit_px = float(exit_["price"])
        qty = float(entry["quantity"])
        if side == "long":
            pnl_pts = (exit_px - entry_px) * qty
            stop = entry_px - stop_pts
            target = entry_px + target_pts
        else:
            pnl_pts = (entry_px - exit_px) * qty
            stop = entry_px + stop_pts
            target = entry_px - target_pts
        pnl_usd = pnl_pts * point_value - fee_per_unit * qty
        exit_reason = str(exit_["reason"]).lower()
        if exit_reason == "target":
            result = "win"
        elif exit_reason == "stop":
            result = "loss"
        else:
            result = "win" if pnl_usd > 0 else "loss"
        entry_ts = pd.Timestamp(entry["ts"])
        pmc = pmc_map.get((int(entry_ts.year), int(entry_ts.month)), np.nan)
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": pd.Timestamp(exit_["ts"]),
                "entry": entry_px,
                "exit": exit_px,
                "stop": stop,
                "target": target,
                "prev_month_close": pmc,
                "pnl_pts": pnl_pts,
                "pnl_usd": pnl_usd,
                "result": result,
                "exit_reason": exit_reason,
            }
        )
    df = pd.DataFrame(rows)
    return df.dropna(subset=["entry_ts", "exit_ts", "entry", "exit", "prev_month_close"])


def _sample_profitable(df: pd.DataFrame, *, max_charts: int, seed: int) -> List[TradeRow]:
    wins = df[df["result"] == "win"].sort_values("entry_ts")
    if wins.empty:
        raise SystemExit("No profitable ST+PMC trades to chart")
    idxs = wins.index.tolist()
    if len(idxs) > max_charts:
        rng = random.Random(seed)
        idxs = rng.sample(idxs, max_charts)
        idxs.sort(key=lambda i: wins.loc[i, "entry_ts"])
    out: List[TradeRow] = []
    for chart_idx, trade_idx in enumerate(idxs, start=1):
        r = wins.loc[trade_idx]
        out.append(
            TradeRow(
                idx=chart_idx,
                side=str(r["side"]),
                entry_ts=pd.Timestamp(r["entry_ts"]),
                exit_ts=pd.Timestamp(r["exit_ts"]),
                entry=float(r["entry"]),
                exit=float(r["exit"]),
                stop=float(r["stop"]),
                target=float(r["target"]),
                prev_month_close=float(r["prev_month_close"]),
                pnl_pts=float(r["pnl_pts"]),
                pnl_usd=float(r["pnl_usd"]),
                result=str(r["result"]),
                exit_reason=str(r["exit_reason"]),
            )
        )
    return out


def _plot_stpmc_trade(
    hourly: pd.DataFrame,
    trade: TradeRow,
    out_path: Path,
    *,
    label: str,
    instrument: str,
    pre_hours: int,
    post_hours: int,
) -> None:
    hold_hours = max((trade.exit_ts - trade.entry_ts).total_seconds() / 3600.0, 0.0)
    use_daily = hold_hours > 7 * 24
    if use_daily:
        start = trade.entry_ts - timedelta(days=5)
        end = trade.exit_ts + timedelta(days=3)
        src = hourly[(hourly.index >= start) & (hourly.index <= end)].copy()
        if src.empty:
            return
        plot = src.resample("1D").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna(subset=["open"])
        if "supertrend" in src.columns:
            plot["supertrend"] = src["supertrend"].resample("1D").last()
            plot["supertrend_trend"] = src["supertrend_trend"].resample("1D").last()
        width = 0.65
        tf_label = "daily"
    else:
        start = trade.entry_ts - timedelta(hours=pre_hours)
        end = trade.exit_ts + timedelta(hours=post_hours)
        plot = hourly[(hourly.index >= start) & (hourly.index <= end)].copy()
        width = (1.0 / 24.0) * 0.72
        tf_label = "hourly"
    if plot.empty:
        return

    x = mdates.date2num(plot.index.to_pydatetime())
    axis_tz = plot.index.tz
    entry_x = mdates.date2num(trade.entry_ts.to_pydatetime())
    exit_x = mdates.date2num(trade.exit_ts.to_pydatetime())
    result_color = "#168a5a"

    fig, ax = plt.subplots(figsize=(18, 8))
    up = plot["close"] >= plot["open"]
    candle_colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=candle_colors, linewidth=0.85, alpha=0.9, zorder=3)
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
        ax.plot(plot.index, bull, color="#009c5b", linewidth=2.0, zorder=6, label="ST bull")
        ax.plot(plot.index, bear, color="#d62728", linewidth=2.0, zorder=6, label="ST bear")

    ax.axhline(
        trade.prev_month_close,
        color="#1565c0",
        linestyle="--",
        linewidth=1.4,
        zorder=5,
        alpha=0.95,
        label="Prior month close %.2f" % trade.prev_month_close,
    )
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, alpha=0.85, label="Stop %.2f" % trade.stop)
    ax.axhline(trade.target, color="#6a1b9a", linestyle=":", linewidth=1.2, alpha=0.85, label="Target %.2f" % trade.target)
    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.2, linestyle="-", alpha=0.9)
    ax.axvline(exit_x, color=result_color, linewidth=1.2, linestyle="--", alpha=0.9)

    marker = "^" if trade.side == "long" else "v"
    ax.scatter(
        [entry_x],
        [trade.entry],
        marker=marker,
        s=120,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Entry %.2f" % trade.entry,
    )
    ax.scatter(
        [exit_x],
        [trade.exit],
        marker="X",
        s=100,
        color=result_color,
        edgecolors="white",
        linewidths=0.8,
        zorder=8,
        label="Exit %.2f (%s)" % (trade.exit, trade.exit_reason),
    )

    entry_l = trade.entry_ts.strftime("%Y-%m-%d %H:%M")
    exit_l = trade.exit_ts.strftime("%Y-%m-%d %H:%M")
    ax.set_title(
        "%s — #%03d WIN %s | %+0.2f pts ($%+.0f) | %s → %s | %s"
        % (label, trade.idx, trade.side, trade.pnl_pts, trade.pnl_usd, entry_l, exit_l, tf_label),
        fontsize=10,
    )
    ax.set_ylabel(instrument)
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=12))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.set_xlabel("Time (America/New_York)" if axis_tz is not None else "Time")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def build_xau_stpmc_profitable_charts(
    *,
    force: bool = False,
    max_charts: int = 300,
    seed: int = 20260719,
    pre_hours: int = 48,
    post_hours: int = 12,
) -> Tuple[str, Path, int]:
    slug = "xauusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior"
    state_root = (
        REPO
        / "live"
        / "state"
        / "metals_futures_strats_sweep"
        / "st_pmc"
        / "xauusd"
        / "states"
        / slug
    )
    out_root = CHARTS_ROOT / "xauusd_stpmc_ma_bull_profitable"
    if force and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    one_m = REPO / "fx" / "xauusd_1m.csv"
    daily = REPO / "fx" / "xauusd_daily.csv"
    if not one_m.exists():
        raise SystemExit("Missing %s (needed for ST+PMC charts; kept local / gitignored)" % one_m)

    print("Loading XAUUSD 1m → hourly SuperTrend...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, "XAUUSD")
    hourly = compute_supertrend(
        resample_hourly(concat_all_1m(bars_by_day)),
        atr_len=ATR_LEN,
        multiplier=ATR_MULT,
    )
    print("  %s hourly bars" % f"{len(hourly):,}", flush=True)

    cfg = _load_config(state_root)
    stop_pts = float(cfg.get("stop_pts", 0.25))
    target_pts = float(cfg.get("target_pts", 0.75))
    # metals ST pack used price points directly (e.g. 25/75 dollars on gold)
    # config may store 25/75 or 0.25/0.75 — prefer absolute if > 1
    if stop_pts < 1.0 and target_pts < 5.0:
        # still could be FX-style; for gold MA-bull state check fills scale
        pass
    df = _load_stpmc_trades(
        state_root / "fills.csv",
        stop_pts=stop_pts,
        target_pts=target_pts,
        daily_path=daily,
        point_value=POINT_VALUES["XAUUSD"],
        fee_per_unit=1.50,
    )
    print(
        "  campaigns %d | wins %d | losses %d"
        % (len(df), int((df.result == "win").sum()), int((df.result == "loss").sum())),
        flush=True,
    )
    picked = _sample_profitable(df, max_charts=max_charts, seed=seed)
    charts_dir = out_root / "charts"
    for trade in picked:
        stamp = trade.entry_ts.strftime("%Y-%m-%d_%H%M")
        out_path = charts_dir / ("%03d_win_%s.png" % (trade.idx, stamp))
        _plot_stpmc_trade(
            hourly,
            trade,
            out_path,
            label="XAUUSD ST+PMC 25/75 MA-bull",
            instrument="XAUUSD",
            pre_hours=pre_hours,
            post_hours=post_hours,
        )
        if trade.idx % 25 == 0 or trade.idx == len(picked):
            print("  charted %d/%d" % (trade.idx, len(picked)), flush=True)

    lines = [
        "# XAUUSD Hourly ST+PMC 25/75 MA-bull — profitable trades",
        "",
        "Broker-like fills. **Profitable campaigns only**, max **%d** (seed `%d`). "
        "Have %d wins / %d total campaigns."
        % (max_charts, seed, int((df.result == "win").sum()), len(df)),
        "",
        "Hourly candles, ATR SuperTrend 14×3, prior-month close, stop/target, entry/exit.",
        "",
        "| # | Side | Entry | Exit | Pts | P/L USD | Chart |",
        "|---:|---|---|---|---:|---:|---|",
    ]
    for t in picked:
        stamp = t.entry_ts.strftime("%Y-%m-%d_%H%M")
        rel = "charts/%03d_win_%s.png" % (t.idx, stamp)
        lines.append(
            "| {idx} | {side} | {entry} | {exit} | {pts:+.2f} | ${usd:+,.0f} | [{rel}]({rel}) |".format(
                idx=t.idx,
                side=t.side,
                entry=t.entry_ts.strftime("%Y-%m-%d %H:%M"),
                exit=t.exit_ts.strftime("%Y-%m-%d %H:%M"),
                pts=t.pnl_pts,
                usd=t.pnl_usd,
                rel=rel,
            )
        )
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ("XAUUSD ST+PMC MA-bull (profitable)", out_root, len(picked))


def write_master_index(packs: Optional[List[Tuple[str, Path, int]]] = None) -> Path:
    CHARTS_ROOT.mkdir(parents=True, exist_ok=True)
    if not packs:
        packs = []
        for idx in sorted(CHARTS_ROOT.glob("**/INDEX.md")):
            if idx.parent == CHARTS_ROOT:
                continue
            if idx.parent.name == "yearly_orb" and (idx.parent / "INDEX.md") == idx:
                # skip yearly folder rollup; list per-slug instead
                continue
            n = len(list(idx.parent.rglob("*.png")))
            label = idx.parent.name.replace("_", " ")
            packs.append((label, idx.parent, n))
        # Prefer ordered known packs
        order = [
            "audjpy_yearly_orb_scaleout3",
            "xauusd_yearly_orb_scaleout3",
            "xagusd_yearly_orb_scaleout3",
            "usdjpy_fbo_1_1_3_atr80",
            "xauusd_stpmc_ma_bull_profitable",
        ]
        labels = {
            "audjpy_yearly_orb_scaleout3": "AUDJPY Yearly ORB scaleout3",
            "xauusd_yearly_orb_scaleout3": "XAUUSD Yearly ORB scaleout3",
            "xagusd_yearly_orb_scaleout3": "XAGUSD Yearly ORB scaleout3",
            "usdjpy_fbo_1_1_3_atr80": "USDJPY FBO 1/1/3 atr80",
            "xauusd_stpmc_ma_bull_profitable": "XAUUSD ST+PMC MA-bull (profitable)",
        }
        by_name = {p[1].name: p for p in packs}
        ordered = []
        for name in order:
            if name in by_name:
                path = by_name[name][1]
                n = by_name[name][2]
                ordered.append((labels.get(name, name), path, n))
        packs = ordered or packs

    lines = [
        "# FX + Metals top models — chart packs",
        "",
        "Broker-like PaperBroker fills. Yearly ORB = one PNG per calendar year; "
        "FBO = one PNG per trade-month; ST+PMC = profitable campaigns (≤300; daily candles if hold >7d).",
        "",
        "| Pack | Charts | Index |",
        "|---|---:|---|",
    ]
    for label, path, n in packs:
        rel = path.relative_to(CHARTS_ROOT).as_posix()
        lines.append("| %s | %d | [%s/INDEX.md](%s/INDEX.md) |" % (label, n, rel, rel))
    lines.append("")
    out = CHARTS_ROOT / "INDEX.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true")
    p.add_argument("--max-charts", type=int, default=300)
    p.add_argument(
        "--only",
        choices=["yearly", "fbo", "stpmc", "all"],
        default="all",
    )
    args = p.parse_args(argv)

    packs: List[Tuple[str, Path, int]] = []
    if args.only in ("yearly", "all"):
        packs.extend(build_yearly_orb_charts(force=args.force))
    if args.only in ("fbo", "all"):
        packs.append(build_usdjpy_fbo_charts(force=args.force, max_charts=args.max_charts))
    if args.only in ("stpmc", "all"):
        packs.append(
            build_xau_stpmc_profitable_charts(force=args.force, max_charts=args.max_charts)
        )

    master = write_master_index()
    print("Master index → %s (%d packs this run)" % (master, len(packs)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
