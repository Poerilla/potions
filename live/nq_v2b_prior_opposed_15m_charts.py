from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .nq_v2b_prior_opposed_replay import DEFAULT_ST_STRATEGY_IDS, PRIOR_OPPOSED_MARKETS, default_st_fills_path
from .replay_audit import POINT_VALUES
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
POINT_VALUE = 20.0
FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class FillTrade:
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    net_usd: float


def _plot_candles(ax, df: pd.DataFrame, *, width_days: float) -> None:
    if df.empty:
        return
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    # Min body must scale with price (0.01 pts is fine on NQ, but 100 pips on EURUSD).
    price_span = float(df["high"].max() - df["low"].min())
    min_body = max(price_span * 0.001, 1e-8)
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=1.0, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                alpha=0.84,
                zorder=4,
            )
        )


def _resample_15m(rth: pd.DataFrame) -> pd.DataFrame:
    if rth.empty:
        return rth
    return (
        rth.resample("15min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def _side_from_entry_side(side: str) -> str:
    return "long" if str(side).lower() == "buy" else "short"


def _load_v2b_trades(fills_path: Path) -> List[FillTrade]:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    trades: List[FillTrade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = _side_from_entry_side(str(entry["side"]))
        entry_px = float(entry["price"])
        net = 0.0
        for _idx, exit_row in exits.iterrows():
            px = float(exit_row["price"])
            qty = int(exit_row["quantity"])
            pts = px - entry_px if side == "long" else entry_px - px
            net += pts * POINT_VALUE * qty - FEE_PER_UNIT * qty
        last_exit = exits.iloc[-1]
        trades.append(
            FillTrade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=pd.Timestamp(entry["ts"]),
                entry_price=entry_px,
                exit_ts=pd.Timestamp(last_exit["ts"]),
                exit_price=float(last_exit["price"]),
                net_usd=net,
            )
        )
    return trades


def _load_st_trades(fills_path: Path, strategy_id: str) -> List[FillTrade]:
    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    trades: List[FillTrade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str).isin(["entry", "runner_entry"])]
        exits = group[~group["reason"].astype(str).isin(["entry", "runner_entry"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_row = exits.iloc[-1]
        side = _side_from_entry_side(str(entry["side"]))
        entry_px = float(entry["price"])
        exit_px = float(exit_row["price"])
        qty = int(entry["quantity"])
        pts = exit_px - entry_px if side == "long" else entry_px - exit_px
        trades.append(
            FillTrade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=pd.Timestamp(entry["ts"]),
                entry_price=entry_px,
                exit_ts=pd.Timestamp(exit_row["ts"]),
                exit_price=exit_px,
                net_usd=pts * POINT_VALUE * qty - FEE_PER_UNIT * max(1, qty),
            )
        )
    return trades


def _load_v2b_fill_groups(fills_path: Path) -> Dict[str, pd.DataFrame]:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    return {str(k): g.sort_values("ts").copy() for k, g in fills.groupby("trade_id")}


def _find_prior_opposite(v2b: FillTrade, st_by_day: Dict[date, List[FillTrade]]) -> Optional[FillTrade]:
    opposite = "short" if v2b.side == "long" else "long"
    candidates = [
        st
        for st in st_by_day.get(v2b.entry_ts.date(), [])
        if st.side == opposite and st.entry_ts < v2b.entry_ts
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.entry_ts)[-1]


def _add_or_levels(ax, rth: pd.DataFrame) -> None:
    opening = rth[
        (rth.index.time >= pd.Timestamp("09:30").time())
        & (rth.index.time < pd.Timestamp("09:45").time())
    ]
    if opening.empty:
        return
    rh = float(opening["high"].max())
    rl = float(opening["low"].min())
    rng = rh - rl
    for value, label, color, style in [
        (rh, "OR high", "#455a64", "-"),
        (rl, "OR low", "#455a64", "-"),
        (rh + rng, "+1R", "#2e7d32", "--"),
        (rl - rng, "-1R", "#c62828", "--"),
        (rh + 2 * rng, "+2R", "#2e7d32", ":"),
        (rl - 2 * rng, "-2R", "#c62828", ":"),
    ]:
        ax.axhline(value, color=color, linestyle=style, linewidth=0.9, alpha=0.65)
        ax.text(rth.index[0], value, " " + label, color=color, fontsize=7, va="bottom")


def _draw_st_trades(ax, trades: List[FillTrade], prior: Optional[FillTrade]) -> None:
    for trade in trades:
        is_prior = prior is not None and trade.trade_id == prior.trade_id
        color = "#d1495b" if trade.side == "short" else "#1b998b"
        alpha = 0.95 if is_prior else 0.38
        size = 115 if is_prior else 46
        marker = "s" if is_prior else "D"
        ax.scatter([trade.entry_ts], [trade.entry_price], s=size, color=color, marker=marker, alpha=alpha, zorder=8)
        ax.scatter([trade.exit_ts], [trade.exit_price], s=max(32, size * 0.55), color=color, marker="x", alpha=alpha, zorder=8)
        ax.plot([trade.entry_ts, trade.exit_ts], [trade.entry_price, trade.exit_price], color=color, linewidth=1.0, alpha=alpha, zorder=7)
        if is_prior:
            ax.axvline(trade.entry_ts, color=color, linewidth=1.25, alpha=0.85)
            ax.text(
                trade.entry_ts,
                trade.entry_price,
                " prior ST+PMC %s" % trade.side,
                color=color,
                fontsize=8,
                va="top",
                zorder=9,
            )


def _draw_v2b_trade(ax, trade: FillTrade, fills: pd.DataFrame) -> None:
    color = "#006dce" if trade.side == "long" else "#7b3fb2"
    marker = "^" if trade.side == "long" else "v"
    ax.scatter([trade.entry_ts], [trade.entry_price], s=120, color=color, marker=marker, zorder=10)
    ax.axvline(trade.entry_ts, color=color, linewidth=1.5, alpha=0.85)
    ax.axvline(trade.exit_ts, color=color, linewidth=1.0, alpha=0.65, linestyle="--")
    exits = fills[fills["reason"].astype(str) != "entry"]
    for _idx, row in exits.iterrows():
        reason = str(row["reason"])
        exit_marker = "o" if reason in {"tp1", "tp2"} else "x"
        ax.scatter([pd.Timestamp(row["ts"])], [float(row["price"])], s=58, color=color, marker=exit_marker, zorder=10)
    ax.text(
        trade.entry_ts,
        trade.entry_price,
        " v2b %s $%.0f" % (trade.side, trade.net_usd),
        color=color,
        fontsize=8,
        va="bottom",
        zorder=11,
    )


def build_charts(
    *,
    market: str,
    output_root: Path,
    v2b_fills: Path,
    st_fills: Path,
    st_strategy_id: str,
    max_charts: Optional[int],
    force: bool,
) -> None:
    global POINT_VALUE
    market = market.lower()
    cfg = MARKETS[market]
    instrument = cfg.instrument
    POINT_VALUE = POINT_VALUES[instrument]
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    v2b_trades = sorted(_load_v2b_trades(v2b_fills), key=lambda item: item.entry_ts)
    if max_charts is not None:
        v2b_trades = v2b_trades[:max_charts]
    v2b_groups = _load_v2b_fill_groups(v2b_fills)
    st_trades = _load_st_trades(st_fills, st_strategy_id)
    st_by_day: Dict[date, List[FillTrade]] = {}
    for trade in st_trades:
        st_by_day.setdefault(trade.entry_ts.date(), []).append(trade)

    print("Loading %s 1m bars..." % instrument, flush=True)
    bars_by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), market)

    rows = []
    violations = 0
    for idx, trade in enumerate(v2b_trades, start=1):
        session = trade.entry_ts.date()
        rth = _rth_bars(bars_by_day.get(session), session)
        if rth.empty:
            continue
        candles = compute_supertrend(_resample_15m(rth), atr_len=14, multiplier=3.0)
        prior = _find_prior_opposite(trade, st_by_day)
        if prior is None:
            violations += 1
        session_st = [
            st
            for st in st_by_day.get(session, [])
            if st.entry_ts <= max(trade.exit_ts, trade.entry_ts) and st.exit_ts >= rth.index[0]
        ]
        fills = v2b_groups[trade.trade_id]

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(17, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        _plot_candles(ax, candles, width_days=(15 / (24 * 60)) * 0.7)
        bull = candles["supertrend"].where(candles["supertrend_trend"] == 1)
        bear = candles["supertrend"].where(candles["supertrend_trend"] == -1)
        ax.plot(candles.index, bull, color="#009c5b", linewidth=1.4, label="15m ST bull")
        ax.plot(candles.index, bear, color="#d62728", linewidth=1.4, label="15m ST bear")
        _add_or_levels(ax, rth)
        _draw_st_trades(ax, session_st, prior)
        _draw_v2b_trade(ax, trade, fills)
        ax.set_title(
            "%s prior-opposed ST+PMC -> v2b S_1_1_3 - %s - %s - net $%.0f"
            % (instrument, session.isoformat(), trade.side, trade.net_usd)
        )
        ax.set_ylabel(instrument)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(15 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        fig.autofmt_xdate()

        rel = Path("charts") / ("%03d_%s_%s_%s.png" % (idx, session.isoformat(), trade.side, "win" if trade.net_usd > 0 else "loss"))
        out = output_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": session.isoformat(),
                "side": trade.side,
                "net": trade.net_usd,
                "v2b_trade_id": trade.trade_id,
                "prior_st_trade_id": prior.trade_id if prior is not None else "",
                "prior_st_side": prior.side if prior is not None else "",
                "chart": str(rel),
            }
        )
        if idx % 50 == 0:
            print("  charted %d/%d" % (idx, len(v2b_trades)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# %s v2b Prior-Opposed ST+PMC 15m Charts" % instrument,
        "",
        "Each chart shows 15m %s RTH candles, 15m Supertrend context, OR levels, same-session ST+PMC trades, and the confirmed v2b `S_1_1_3` campaign." % instrument,
        "",
        "The large square is the causal prior ST+PMC entry in the opposite direction. Smaller diamonds are other same-session ST+PMC trades. The triangle is the v2b entry, circles are TP exits, and x markers are stops/EOD exits.",
        "",
        "- Source replay: `live/state/%s_v2b_prior_opposed_stpmc_broker_like/`" % market,
        "- ST+PMC source: `%s`" % st_strategy_id,
        "- Charts built: **%d**" % len(rows),
        "- Missing prior-opposite validations during chart build: **%d**" % violations,
        "",
        "| # | Session | Side | Net | Prior ST+PMC | Chart |",
        "|---:|---|---|---:|---|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${net:,.2f} | {prior_st_side} | [{chart}]({chart}) |".format(**item)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build 15m charts for a broker-like prior-opposed ST+PMC v2b replay.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--v2b-fills",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--st-fills",
        type=Path,
        default=None,
    )
    parser.add_argument("--st-strategy-id", default=None)
    parser.add_argument("--max-charts", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    market = args.market.lower()
    output_root = args.output_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/charts/prior_opposed_15m"
    v2b_fills = args.v2b_fills or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/states/{market}_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv"
    st_fills = args.st_fills or default_st_fills_path(market)
    st_strategy_id = args.st_strategy_id or DEFAULT_ST_STRATEGY_IDS[market]
    build_charts(
        market=market,
        output_root=output_root,
        v2b_fills=v2b_fills,
        st_fills=st_fills,
        st_strategy_id=st_strategy_id,
        max_charts=args.max_charts,
        force=not args.no_force,
    )
    print("Wrote %s" % (output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
