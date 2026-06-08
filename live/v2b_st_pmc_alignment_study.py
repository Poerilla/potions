from __future__ import annotations

import argparse
import csv
import math
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, load_prev_month_close_map, resample_hourly


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"


@dataclass(frozen=True)
class Trade:
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    exit_reason: str
    pnl_usd: float
    pnl_pts: float
    session: str


@dataclass(frozen=True)
class AlignmentRow:
    trade: Trade
    category: str
    v2b_directions: str
    v2b_entry_count: int
    v2b_net_usd: float
    chart: str


def load_strategy_trades(fills_path: Path, *, strategy_id: str, point_value: float, fee_per_unit: float) -> List[Trade]:
    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    if fills.empty:
        raise FileNotFoundError("No fills for %s in %s" % (strategy_id, fills_path))
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)

    out: List[Trade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str).isin(["entry", "runner_entry"])]
        exits = group[~group["reason"].astype(str).isin(["entry", "runner_entry"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_row = exits.iloc[-1]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        exit_px = float(exit_row["price"])
        qty = int(entry.get("quantity") or 1)
        pnl_pts = (exit_px - entry_px) if side == "long" else (entry_px - exit_px)
        pnl_usd = pnl_pts * point_value * qty - fee_per_unit * max(1, qty)
        entry_ts = pd.Timestamp(entry["ts"])
        exit_ts = pd.Timestamp(exit_row["ts"])
        out.append(
            Trade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                entry=entry_px,
                exit=exit_px,
                exit_reason=str(exit_row["reason"]),
                pnl_usd=pnl_usd,
                pnl_pts=pnl_pts,
                session=entry_ts.date().isoformat(),
            )
        )
    return out


def load_v2b_trades(fills_path: Path, *, point_value: float, fee_per_unit: float) -> Dict[str, List[Trade]]:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)

    by_session: Dict[str, List[Trade]] = {}
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_qty = int(entry.get("quantity") or 1)
        entry_px = float(entry["price"])
        pnl = 0.0
        qty_closed = 0
        exit_ts = pd.Timestamp(exits.iloc[-1]["ts"])
        exit_px = float(exits.iloc[-1]["price"])
        exit_reason = str(exits.iloc[-1]["reason"])
        for _idx, row in exits.iterrows():
            qty = int(row.get("quantity") or 1)
            px = float(row["price"])
            pts = (px - entry_px) if side == "long" else (entry_px - px)
            pnl += pts * point_value * qty - fee_per_unit * qty
            qty_closed += qty
        if qty_closed <= 0:
            continue
        entry_ts = pd.Timestamp(entry["ts"])
        trade = Trade(
            trade_id=str(trade_id),
            side=side,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            entry=entry_px,
            exit=exit_px,
            exit_reason=exit_reason,
            pnl_usd=pnl,
            pnl_pts=pnl / point_value,
            session=entry_ts.date().isoformat(),
        )
        by_session.setdefault(trade.session, []).append(trade)
    return by_session


def classify(st_trade: Trade, v2b_by_session: Dict[str, List[Trade]]) -> tuple[str, str, int, float]:
    v2b = v2b_by_session.get(st_trade.session, [])
    if not v2b:
        return "no_v2b", "", 0, 0.0
    directions = sorted({t.side for t in v2b})
    net = sum(t.pnl_usd for t in v2b)
    if st_trade.side in directions:
        return "aligned", ",".join(directions), len(v2b), net
    return "opposed", ",".join(directions), len(v2b), net


def summarize(rows: Sequence[AlignmentRow]) -> List[Dict[str, str]]:
    out = []
    for category in ["aligned", "opposed", "no_v2b", "not_aligned", "all"]:
        subset = list(rows) if category == "all" else (
            [r for r in rows if r.category != "aligned"] if category == "not_aligned" else [r for r in rows if r.category == category]
        )
        if not subset:
            continue
        net = sum(r.trade.pnl_usd for r in subset)
        wins = sum(1 for r in subset if r.trade.pnl_usd > 0)
        losses = len(subset) - wins
        gross_win = sum(r.trade.pnl_usd for r in subset if r.trade.pnl_usd > 0)
        gross_loss = abs(sum(r.trade.pnl_usd for r in subset if r.trade.pnl_usd <= 0))
        out.append(
            {
                "category": category,
                "trades": str(len(subset)),
                "wins": str(wins),
                "losses": str(losses),
                "win_rate_pct": "%.2f" % (100.0 * wins / len(subset)),
                "net_usd": "%.2f" % net,
                "avg_usd": "%.2f" % (net / len(subset)),
                "profit_factor": "%.3f" % (gross_win / gross_loss if gross_loss else math.inf),
                "v2b_net_same_days": "%.2f" % sum(r.v2b_net_usd for r in subset),
            }
        )
    return out


def load_hourly_context(dbn_path: Path, daily_path: Path, market: str) -> pd.DataFrame:
    gby = load_1m_by_ny_date_any(dbn_path.resolve(), market)
    hourly = resample_hourly(concat_all_1m(gby))
    hourly = compute_supertrend(hourly, atr_len=14, multiplier=3.0)
    pmc_map = load_prev_month_close_map(daily_path)
    hourly["prev_month_close"] = [pmc_map.get((int(ts.year), int(ts.month)), np.nan) for ts in hourly.index]
    return hourly


def plot_candles(ax, df: pd.DataFrame, *, width_days: float, alpha: float = 0.85) -> None:
    if df.empty:
        return
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.7, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), 0.01)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.3,
                alpha=alpha,
                zorder=4,
            )
        )


def plot_alignment_chart(
    *,
    row: AlignmentRow,
    st_hourly: pd.DataFrame,
    v2b_day_bars: Optional[pd.DataFrame],
    v2b_trades: Sequence[Trade],
    out_path: Path,
    instrument: str,
    st_label: str,
    v2b_label: str,
) -> None:
    trade = row.trade
    start = trade.entry_ts - timedelta(hours=30)
    end = trade.exit_ts + timedelta(hours=18)
    h = st_hourly[(st_hourly.index >= start) & (st_hourly.index <= end)].copy()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10), gridspec_kw={"height_ratios": [3, 2]})

    if not h.empty:
        plot_candles(ax1, h, width_days=(1 / 24) * 0.72)
        bull = h["supertrend"].where(h["supertrend_trend"] == 1)
        bear = h["supertrend"].where(h["supertrend_trend"] == -1)
        ax1.plot(h.index, bull, color="#009c5b", linewidth=1.8, label="%s hourly ST bull" % instrument)
        ax1.plot(h.index, bear, color="#d62728", linewidth=1.8, label="%s hourly ST bear" % instrument)
        if "prev_month_close" in h and h["prev_month_close"].notna().any():
            ax1.plot(h.index, h["prev_month_close"], color="#1565c0", linestyle="--", linewidth=1.2, label="%s prior month close" % instrument)
    color = "#168a5a" if trade.pnl_usd > 0 else "#c43d3d"
    ax1.axvline(trade.entry_ts, color=color, linewidth=1.1)
    ax1.axvline(trade.exit_ts, color=color, linewidth=1.1, linestyle="--")
    ax1.scatter([trade.entry_ts], [trade.entry], marker="^" if trade.side == "long" else "v", s=100, color=color, edgecolors="white", zorder=8)
    ax1.scatter([trade.exit_ts], [trade.exit], marker="X", s=90, color=color, edgecolors="white", zorder=8)
    ax1.set_title(
        "%s %s | %s | %s | PnL $%+.0f | %s %s"
        % (instrument, st_label, trade.session, row.category, trade.pnl_usd, v2b_label, row.v2b_directions or "none"),
        fontsize=10,
    )
    ax1.set_ylabel(instrument)
    ax1.grid(True, color="#dddddd", linewidth=0.5, alpha=0.7)
    ax1.legend(loc="upper left", fontsize=7, ncol=3)

    if v2b_day_bars is not None and not v2b_day_bars.empty:
        d = v2b_day_bars.copy()
        plot_candles(ax2, d, width_days=(1 / (24 * 60)) * 0.78)
        or_slice = d[(d.index.time >= pd.Timestamp("09:30").time()) & (d.index.time < pd.Timestamp("09:45").time())]
        if not or_slice.empty:
            rh = float(or_slice["high"].max())
            rl = float(or_slice["low"].min())
            rng = rh - rl
            for y, label, color2, style in [
                (rh, "OR high", "#1565c0", "-"),
                (rl, "OR low", "#1565c0", "-"),
                (rh + rng, "Long TP1 / range extension", "#6a1b9a", "--"),
                (rl - rng, "Short TP1 / range extension", "#6a1b9a", "--"),
                (rh + 2 * rng, "Long 2R", "#9c27b0", ":"),
                (rl - 2 * rng, "Short 2R", "#9c27b0", ":"),
            ]:
                ax2.axhline(y, color=color2, linestyle=style, linewidth=1.0, alpha=0.85, label=label)
        for vt in v2b_trades:
            c = "#168a5a" if vt.side == "long" else "#c43d3d"
            ax2.axvline(vt.entry_ts, color=c, linewidth=1.0, alpha=0.8)
            ax2.scatter([vt.entry_ts], [vt.entry], marker="^" if vt.side == "long" else "v", s=70, color=c, edgecolors="white", zorder=8)
            ax2.scatter([vt.exit_ts], [vt.exit], marker="X", s=60, color=c, edgecolors="white", zorder=8)
        ax2.xaxis.set_major_locator(mdates.MinuteLocator(interval=30, tz=d.index.tz))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=d.index.tz))
    ax2.set_title("%s %s same-session extended opening range" % (instrument, v2b_label), fontsize=10)
    ax2.set_ylabel(instrument)
    ax2.set_xlabel("Time (America/New_York)")
    ax2.grid(True, color="#dddddd", linewidth=0.5, alpha=0.7)
    handles, labels = ax2.get_legend_handles_labels()
    if handles:
        by_label = dict(zip(labels, handles))
        ax2.legend(by_label.values(), by_label.keys(), loc="upper left", fontsize=7, ncol=3)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_index(
    out_root: Path,
    rows: Sequence[AlignmentRow],
    summary_rows: Sequence[Dict[str, str]],
    *,
    instrument: str,
    st_label: str,
    v2b_label: str,
) -> None:
    lines = [
        "# %s ST+PMC vs %s v2b Alignment Study" % (instrument, instrument),
        "",
        "ST+PMC proxy: `%s`." % st_label,
        "V2B proxy: `%s`." % v2b_label,
        "",
        "Alignment is by NY session date and direction:",
        "",
        "- `aligned`: ST+PMC trade direction appears in same-day v2b campaigns.",
        "- `opposed`: v2b traded only the opposite direction.",
        "- `no_v2b`: no v2b entry on that session.",
        "",
        "## Summary",
        "",
        "| Category | Trades | Win % | Net | Avg | PF | Same-day v2b net |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary_rows:
        lines.append(
            "| {category} | {trades} | {win_rate_pct}% | ${net_usd} | ${avg_usd} | {profit_factor} | ${v2b_net_same_days} |".format(**r)
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "| # | Date | Category | ST Side | ST PnL | V2B dirs | V2B entries | Chart |",
            "|---:|---|---|---|---:|---|---:|---|",
        ]
    )
    for idx, row in enumerate(rows, start=1):
        rel = row.chart
        lines.append(
            f"| {idx} | {row.trade.session} | {row.category} | {row.trade.side} | "
            f"${row.trade.pnl_usd:,.0f} | {row.v2b_directions or '-'} | {row.v2b_entry_count} | [{Path(rel).name}]({rel}) |"
        )
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def build_study(
    *,
    output_root: Path,
    market: str,
    st_strategy_id: str,
    st_label: str,
    v2b_fills: Path,
    v2b_label: str,
    max_charts: Optional[int] = None,
    force: bool = True,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    configs = {
        "mnq": {
            "instrument": "MNQ",
            "daily": REPO / "mnq/mnq_daily.csv",
            "dbn": REPO / "mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst",
            "point_value": 2.0,
        },
        "mym": {
            "instrument": "MYM",
            "daily": REPO / "mym/mym_daily.csv",
            "dbn": REPO / "mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
            "point_value": 0.5,
        },
    }
    cfg = configs[market]
    instrument = str(cfg["instrument"])
    daily_path = Path(cfg["daily"])
    dbn_path = Path(cfg["dbn"])
    point_value = float(cfg["point_value"])
    st_fills = REPO / f"live/state/hourly_st_pmc_strategyplugin_variants_cross_market/{market}/combined_state/fills.csv"

    st_trades = [
        t for t in load_strategy_trades(st_fills, strategy_id=st_strategy_id, point_value=point_value, fee_per_unit=1.50)
        if t.entry_ts.date() >= date(2021, 3, 4)
    ]
    st_trades = sorted(st_trades, key=lambda t: (t.entry_ts, t.trade_id))
    v2b_by_session = load_v2b_trades(v2b_fills, point_value=point_value, fee_per_unit=1.50)

    rows: List[AlignmentRow] = []
    for trade in st_trades:
        category, directions, count, v2b_net = classify(trade, v2b_by_session)
        rows.append(AlignmentRow(trade, category, directions, count, v2b_net, ""))

    summary_rows = summarize(rows)
    write_csv(output_root / "summary.csv", summary_rows)
    write_csv(
        output_root / "trades.csv",
        [
            {
                "session": r.trade.session,
                "category": r.category,
                "st_side": r.trade.side,
                "st_entry_ts": r.trade.entry_ts.isoformat(),
                "st_exit_ts": r.trade.exit_ts.isoformat(),
                "st_entry": "%.6f" % r.trade.entry,
                "st_exit": "%.6f" % r.trade.exit,
                "st_exit_reason": r.trade.exit_reason,
                "st_pnl_usd": "%.2f" % r.trade.pnl_usd,
                "v2b_directions": r.v2b_directions,
                "v2b_entry_count": str(r.v2b_entry_count),
                "v2b_net_usd": "%.2f" % r.v2b_net_usd,
            }
            for r in rows
        ],
    )

    print("Loading %s 1m/hourly chart context..." % instrument, flush=True)
    v2b_gby = load_1m_by_ny_date_any(dbn_path.resolve(), market)
    st_hourly = resample_hourly(concat_all_1m(v2b_gby))
    st_hourly = compute_supertrend(st_hourly, atr_len=14, multiplier=3.0)
    pmc_map = load_prev_month_close_map(daily_path)
    st_hourly["prev_month_close"] = [pmc_map.get((int(ts.year), int(ts.month)), np.nan) for ts in st_hourly.index]

    chart_rows = rows if max_charts is None else rows[:max_charts]
    with_charts: List[AlignmentRow] = []
    for idx, row in enumerate(chart_rows, start=1):
        day = date.fromisoformat(row.trade.session)
        v2b_day_bars = v2b_gby.get(day)
        v2b_day = v2b_by_session.get(row.trade.session, [])
        subdir = "aligned" if row.category == "aligned" else "not_aligned" if row.category in {"opposed", "no_v2b"} else row.category
        rel = Path("charts") / subdir / ("%04d_%s_%s_%s.png" % (idx, row.trade.session, row.category, row.trade.side))
        plot_alignment_chart(
            row=row,
            st_hourly=st_hourly,
            v2b_day_bars=v2b_day_bars,
            v2b_trades=v2b_day,
            out_path=output_root / rel,
            instrument=instrument,
            st_label=st_label,
            v2b_label=v2b_label,
        )
        with_charts.append(AlignmentRow(row.trade, row.category, row.v2b_directions, row.v2b_entry_count, row.v2b_net_usd, str(rel)))
        if idx % 100 == 0:
            print("  charted %d/%d" % (idx, len(chart_rows)), flush=True)

    write_index(output_root, with_charts, summary_rows, instrument=instrument, st_label=st_label, v2b_label=v2b_label)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Study MYM ST+PMC days that align with MNQ v2b.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/v2b_st_pmc_alignment_study")
    parser.add_argument("--market", default="mnq", choices=["mnq", "mym"])
    parser.add_argument("--st-strategy-id", default="mnq_hourly_st_pmc_sl25_tp75_3r")
    parser.add_argument("--st-label", default="hourly ST+PMC sl25_tp75_3r")
    parser.add_argument(
        "--v2b-fills",
        type=Path,
        default=REPO / "live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_3/fills.csv",
    )
    parser.add_argument("--v2b-label", default="v2b S_1_1_3")
    parser.add_argument("--max-charts", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_study(
        output_root=args.output_root,
        market=args.market,
        st_strategy_id=args.st_strategy_id,
        st_label=args.st_label,
        v2b_fills=args.v2b_fills,
        v2b_label=args.v2b_label,
        max_charts=args.max_charts,
        force=not args.no_force,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
