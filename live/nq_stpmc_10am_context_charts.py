from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_nq_1m_10am_open_sample_charts import plot_candles, ten_am_open
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_prev_month_close_map, resample_hourly


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
POINT_VALUE = 20.0
FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class Trade:
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    net_usd: float
    source: str


def load_fill_trades(fills_path: Path, strategy_id: str, source: str) -> List[Trade]:
    fills = pd.read_csv(fills_path)
    if "strategy_id" in fills.columns:
        fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    trades: List[Trade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str).isin(["entry", "runner_entry"])]
        exits = group[~group["reason"].astype(str).isin(["entry", "runner_entry"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_price = float(entry["price"])
        net = 0.0
        for _idx, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_price if side == "long" else entry_price - px
            net += pts * POINT_VALUE * qty - FEE_PER_UNIT * qty
        exit_row = exits.iloc[-1]
        trades.append(
            Trade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=pd.Timestamp(entry["ts"]),
                entry_price=entry_price,
                exit_ts=pd.Timestamp(exit_row["ts"]),
                exit_price=float(exit_row["price"]),
                net_usd=net,
                source=source,
            )
        )
    return trades


def by_entry_session(trades: Sequence[Trade]) -> Dict[date, List[Trade]]:
    out: Dict[date, List[Trade]] = {}
    for trade in trades:
        out.setdefault(trade.entry_ts.date(), []).append(trade)
    return {day: sorted(items, key=lambda t: t.entry_ts) for day, items in out.items()}


def pre10_opposite_v2b_sessions(st_by_day: Dict[date, List[Trade]], v2b_by_day: Dict[date, List[Trade]]) -> Dict[date, List[Trade]]:
    cutoff = time(10, 0)
    out: Dict[date, List[Trade]] = {}
    for day, st_trades in st_by_day.items():
        st_sides = {t.side for t in st_trades}
        matches = [
            v
            for v in v2b_by_day.get(day, [])
            if v.entry_ts.time() < cutoff and (("long" if v.side == "short" else "short") in st_sides)
        ]
        if matches:
            out[day] = matches
    return out


def hourly_context_from_loaded_1m(by_day: Dict[date, pd.DataFrame], daily_path: Path) -> pd.DataFrame:
    hourly = resample_hourly(concat_all_1m(by_day))
    hourly = compute_supertrend(hourly, atr_len=14, multiplier=3.0)
    pmc = load_prev_month_close_map(daily_path)
    hourly["prev_month_close"] = [pmc.get((int(ts.year), int(ts.month)), np.nan) for ts in hourly.index]
    return hourly


def chart_window(day_df: pd.DataFrame, day: date, st_trades: Sequence[Trade]) -> pd.DataFrame:
    rth_start = pd.Timestamp.combine(day, time(9, 30)).tz_localize(NY)
    rth_end = pd.Timestamp.combine(day, time(16, 0)).tz_localize(NY)
    earliest = min([t.entry_ts for t in st_trades] + [rth_start])
    start = min(rth_start, earliest - timedelta(minutes=30))
    return day_df[(day_df.index >= start) & (day_df.index <= rth_end)].copy()


def draw_trades(ax, trades: Sequence[Trade], label_prefix: str, *, alpha: float = 0.95) -> None:
    for trade in trades:
        color = "#1b998b" if trade.side == "long" else "#d1495b"
        marker = "^" if trade.side == "long" else "v"
        ax.scatter([trade.entry_ts], [trade.entry_price], color=color, marker=marker, s=110, alpha=alpha, zorder=10)
        ax.axvline(trade.entry_ts, color=color, linewidth=1.0, alpha=0.65, zorder=5)
        if trade.exit_ts.date() == trade.entry_ts.date():
            ax.scatter([trade.exit_ts], [trade.exit_price], color=color, marker="x", s=75, alpha=alpha, zorder=10)
            ax.plot([trade.entry_ts, trade.exit_ts], [trade.entry_price, trade.exit_price], color=color, linewidth=1.0, alpha=0.75, zorder=8)
        ax.annotate(
            "%s %s $%.0f" % (label_prefix, trade.side, trade.net_usd),
            xy=(trade.entry_ts, trade.entry_price),
            xytext=(8, 18 if trade.side == "long" else -26),
            textcoords="offset points",
            color=color,
            fontsize=7,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 0.65},
            zorder=11,
        )


def draw_10am_context(ax, rth: pd.DataFrame, day: date) -> Optional[float]:
    marker = ten_am_open(rth)
    ten = pd.Timestamp.combine(day, time(10, 0)).tz_localize(NY)
    eleven = pd.Timestamp.combine(day, time(11, 0)).tz_localize(NY)
    ax.axvline(ten, color="#0057b8", linewidth=1.25, linestyle="--", alpha=0.85, label="10:00")
    ax.axvline(eleven, color="#6a1b9a", linewidth=1.25, linestyle="--", alpha=0.8, label="11:00")
    if marker is None:
        return None
    marker_ts, marker_open = marker
    ax.axhline(marker_open, color="#0057b8", linewidth=1.2, alpha=0.75, label="10:00 open")
    ax.text(marker_ts, marker_open, " 10:00 open %.2f" % marker_open, color="#0057b8", fontsize=8, va="bottom")
    return marker_open


def draw_hourly_context(ax, hourly: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> None:
    h = hourly[(hourly.index >= start - timedelta(hours=2)) & (hourly.index <= end)].copy()
    if h.empty:
        return
    bull = h["supertrend"].where(h["supertrend_trend"] == 1)
    bear = h["supertrend"].where(h["supertrend_trend"] == -1)
    ax.step(h.index, bull, where="post", color="#009c5b", linewidth=1.25, label="1h ST bull")
    ax.step(h.index, bear, where="post", color="#d62728", linewidth=1.25, label="1h ST bear")
    if h["prev_month_close"].notna().any():
        ax.step(h.index, h["prev_month_close"], where="post", color="#263238", linestyle=":", linewidth=1.15, label="PMC")


def write_chart_set(
    *,
    output_root: Path,
    days: Sequence[date],
    st_by_day: Dict[date, List[Trade]],
    v2b_by_day: Dict[date, List[Trade]],
    v2b_overlay_by_day: Dict[date, List[Trade]],
    bars_by_day: Dict[date, pd.DataFrame],
    hourly: pd.DataFrame,
    title: str,
    force: bool,
    max_charts: Optional[int],
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)
    rows: List[dict[str, object]] = []
    selected = sorted(days)
    if max_charts is not None:
        selected = selected[:max_charts]
    for idx, day in enumerate(selected, start=1):
        day_df = bars_by_day.get(day)
        rth = _rth_bars(day_df, day)
        st_trades = st_by_day.get(day, [])
        if day_df is None or day_df.empty or rth.empty or not st_trades:
            continue
        plot_df = chart_window(day_df, day, st_trades)
        if plot_df.empty:
            continue
        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(19, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        plot_candles(ax, plot_df, width_days=(1 / (24 * 60)) * 0.72)
        draw_hourly_context(ax, hourly, plot_df.index[0], plot_df.index[-1])
        marker_open = draw_10am_context(ax, rth, day)
        draw_trades(ax, st_trades, "ST+PMC")
        overlay_v2b = v2b_overlay_by_day.get(day, [])
        if overlay_v2b:
            draw_trades(ax, overlay_v2b, "pre10 V2B", alpha=0.8)
        ax.set_title("%s - %s - ST trades %d - pre10 opposing V2B %d" % (title, day.isoformat(), len(st_trades), len(overlay_v2b)))
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e2e2e2", linewidth=0.55, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8, ncol=3)

        colors = np.where(plot_df["close"] >= plot_df["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(plot_df.index, plot_df["volume"], width=(1 / (24 * 60)) * 0.72, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30], tz=plot_df.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=plot_df.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        fig.autofmt_xdate()

        st_net = sum(t.net_usd for t in st_trades)
        v2b_net = sum(t.net_usd for t in overlay_v2b)
        rel = Path("charts") / ("%04d_%s_st%s_v2b%s.png" % (idx, day.isoformat(), len(st_trades), len(overlay_v2b)))
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": day.isoformat(),
                "st_trades": len(st_trades),
                "st_sides": ",".join(sorted({t.side for t in st_trades})),
                "st_net": st_net,
                "pre10_opposing_v2b": len(overlay_v2b),
                "pre10_opposing_v2b_net": v2b_net,
                "ten_open": marker_open if marker_open is not None else "",
                "chart": str(rel),
            }
        )
        if idx % 100 == 0:
            print("  charted %d/%d in %s" % (idx, len(selected), output_root), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# %s" % title,
        "",
        "One chart per NQ session with `nq_hourly_st_pmc_sl25_tp75_3r` trades. Candles are 1-minute bars, the horizontal blue line is the 10:00 ET candle open, and the vertical lines mark 10:00 and 11:00 ET.",
        "",
        "When this chart set includes V2B overlays, they use `nq_v2b_sizing_S_1_1_3` and are included only when they occur before 10:00 ET and oppose at least one same-session ST+PMC trade.",
        "",
        "- Charts built: **%d**" % len(rows),
        "",
        "| # | Session | ST trades | ST sides | ST net | Pre10 opposing V2B | Chart |",
        "|---:|---|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {session} | {st_trades} | {st_sides} | ${st_net:,.2f} | {pre10_opposing_v2b} | [{chart}]({chart}) |".format(**row)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def build(
    *,
    output_root: Path,
    st_fills: Path,
    v2b_fills: Path,
    st_strategy_id: str,
    v2b_strategy_id: str,
    max_charts: Optional[int],
    force: bool,
) -> None:
    st_trades = load_fill_trades(st_fills, st_strategy_id, "st_pmc")
    v2b_trades = load_fill_trades(v2b_fills, v2b_strategy_id, "v2b")
    st_by_day = by_entry_session(st_trades)
    v2b_by_day = by_entry_session(v2b_trades)
    opposing_v2b = pre10_opposite_v2b_sessions(st_by_day, v2b_by_day)

    cfg = MARKETS["nq"]
    print("Loading NQ 1m bars...", flush=True)
    bars_by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), "nq")
    print("Computing hourly ST+PMC context...", flush=True)
    hourly = hourly_context_from_loaded_1m(bars_by_day, cfg.daily_path)

    all_days = sorted(day for day in st_by_day if day in bars_by_day)
    subset_days = sorted(day for day in all_days if day in opposing_v2b)
    print("ST+PMC sessions: %d; pre10 opposing V2B subset: %d" % (len(all_days), len(subset_days)), flush=True)

    write_chart_set(
        output_root=output_root / "all_stpmc_1m",
        days=all_days,
        st_by_day=st_by_day,
        v2b_by_day=v2b_by_day,
        v2b_overlay_by_day={},
        bars_by_day=bars_by_day,
        hourly=hourly,
        title="NQ ST+PMC Trade Days - 1m 10:00 Context",
        force=force,
        max_charts=max_charts,
    )
    write_chart_set(
        output_root=output_root / "opposing_v2b_pre10_1m",
        days=subset_days,
        st_by_day=st_by_day,
        v2b_by_day=v2b_by_day,
        v2b_overlay_by_day=opposing_v2b,
        bars_by_day=bars_by_day,
        hourly=hourly,
        title="NQ ST+PMC Days With Pre-10 Opposing V2B - 1m 10:00 Context",
        force=force,
        max_charts=max_charts,
    )
    lines = [
        "# NQ ST+PMC / 10:00 Context Chart Packs",
        "",
        "- All ST+PMC trade days: [`all_stpmc_1m/INDEX.md`](all_stpmc_1m/INDEX.md)",
        "- ST+PMC days with a pre-10:00 opposite V2B entry: [`opposing_v2b_pre10_1m/INDEX.md`](opposing_v2b_pre10_1m/INDEX.md)",
        "",
        "| Set | Sessions |",
        "|---|---:|",
        "| ST+PMC trade days | %d |" % len(all_days),
        "| Pre-10 opposing V2B subset | %d |" % len(subset_days),
        "",
        "Sources:",
        "",
        "- ST+PMC fills: `%s` / `%s`" % (st_fills, st_strategy_id),
        "- V2B fills: `%s` / `%s`" % (v2b_fills, v2b_strategy_id),
        "",
    ]
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build NQ ST+PMC 1m charts with 10:00 context and pre-10 opposing V2B subset.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/nq_stpmc_10am_context_charts")
    parser.add_argument("--st-fills", type=Path, default=REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/combined_state/fills.csv")
    parser.add_argument("--st-strategy-id", default="nq_hourly_st_pmc_sl25_tp75_3r")
    parser.add_argument("--v2b-fills", type=Path, default=REPO / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/fills.csv")
    parser.add_argument("--v2b-strategy-id", default="nq_v2b_sizing_S_1_1_3")
    parser.add_argument("--max-charts", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build(
        output_root=args.output_root,
        st_fills=args.st_fills,
        v2b_fills=args.v2b_fills,
        st_strategy_id=args.st_strategy_id,
        v2b_strategy_id=args.v2b_strategy_id,
        max_charts=args.max_charts,
        force=not args.no_force,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
