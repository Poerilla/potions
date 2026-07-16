from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
from .store import FlatFileStore
from .nq_v2b_prior_opposed_replay import default_st_orders_path, load_st_events
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, _rth_bars, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .v2b_st_pmc_alignment_study import REPO
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_prev_month_close_map, resample_hourly


NY = "America/New_York"
FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class Trade:
    trade_id: str
    strategy_id: str
    source: str
    side: str
    qty: int
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    exit_reason: str
    net_usd: float


@dataclass(frozen=True)
class Summary:
    label: str
    trades: int
    units: int
    net_usd: float
    closed_dd_usd: float
    stress_dd_usd: float
    win_rate_pct: float
    profit_factor: float
    max_open_units: int

    @property
    def net_over_stress(self) -> float:
        return self.net_usd / abs(self.stress_dd_usd) if self.stress_dd_usd else 0.0


def money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def run_gated_v2b(market: str, output_root: Path, *, force: bool) -> Path:
    cfg = MARKETS[market]
    state_root = output_root / market / "states" / ("%s_v2b_prior_opposed_stpmc_only_S_1_1_3" % market)
    if state_root.exists() and not force and (state_root / "fills.csv").exists():
        return state_root
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.parent.mkdir(parents=True, exist_ok=True)

    st_strategy_id = "%s_hourly_st_pmc_sl25_tp75_3r" % market
    st_fills = REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market" / market / "combined_state/fills.csv"
    st_orders = default_st_orders_path(market, st_fills)
    print("Loading %s 1m bars..." % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    if st_orders.exists():
        st_events = load_st_events(
            st_fills,
            st_strategy_id,
            orders_path=st_orders,
            bars_by_ny_date=gby,
        )
    else:
        st_events = load_st_events(st_fills, st_strategy_id)
    regime_dates = _regime_dates(cfg, gby, start=date(2021, 3, 4))
    regime_dates_iso = [d.isoformat() for d in regime_dates]

    strategy_id = "%s_v2b_prior_opposed_stpmc_only_S_1_1_3" % market
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=cfg.instrument,
        broker_instrument=cfg.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=64,
        config_json=json.dumps(
            {
                "market": market,
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "tick_size": 0.25,
                "use_regime_filter": True,
                "start": "2021-03-04",
                "regime_dates": regime_dates_iso,
                "record_levels": False,
                "dynamic_sizing_events": st_events,
                "prior_opposite_only": True,
                "prior_opposite_entry_qty": 5,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=1.0)
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        df = _rth_bars(gby.get(day), day)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=cfg.instrument,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(cfg.dbn_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 500 == 0:
            print("  %s %d/%d sessions" % (cfg.instrument, idx, len(regime_dates)), flush=True)
    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=cfg.instrument,
        fee_per_unit=FEE_PER_UNIT,
    )
    return state_root


def load_st_trades(market: str, strategy_id: str) -> List[Trade]:
    fills_path = REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market" / market / "combined_state/fills.csv"
    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    point_value = POINT_VALUES[MARKETS[market].instrument]
    trades: List[Trade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str).isin(["entry", "runner_entry"])]
        exits = group[~group["reason"].astype(str).isin(["entry", "runner_entry"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_row = exits.iloc[-1]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        qty = int(entry["quantity"])
        entry_price = float(entry["price"])
        exit_price = float(exit_row["price"])
        points = exit_price - entry_price if side == "long" else entry_price - exit_price
        trades.append(
            Trade(
                trade_id=str(trade_id),
                strategy_id=strategy_id,
                source="st_pmc",
                side=side,
                qty=qty,
                entry_ts=pd.Timestamp(entry["ts"]),
                entry_price=entry_price,
                exit_ts=pd.Timestamp(exit_row["ts"]),
                exit_price=exit_price,
                exit_reason=str(exit_row["reason"]),
                net_usd=points * point_value * qty - FEE_PER_UNIT * qty,
            )
        )
    return sorted(trades, key=lambda t: (t.entry_ts, t.trade_id))


def load_v2b_trades(state_root: Path, market: str) -> List[Trade]:
    strategy_id = "%s_v2b_prior_opposed_stpmc_only_S_1_1_3" % market
    fills = pd.read_csv(state_root / "fills.csv")
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    point_value = POINT_VALUES[MARKETS[market].instrument]
    trades: List[Trade] = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_price = float(entry["price"])
        net = 0.0
        for _idx, row in exits.iterrows():
            qty = int(row["quantity"])
            price = float(row["price"])
            points = price - entry_price if side == "long" else entry_price - price
            net += points * point_value * qty - FEE_PER_UNIT * qty
        last_exit = exits.iloc[-1]
        trades.append(
            Trade(
                trade_id=str(trade_id),
                strategy_id=strategy_id,
                source="v2b",
                side=side,
                qty=int(entry["quantity"]),
                entry_ts=pd.Timestamp(entry["ts"]),
                entry_price=entry_price,
                exit_ts=pd.Timestamp(last_exit["ts"]),
                exit_price=float(last_exit["price"]),
                exit_reason=str(last_exit["reason"]),
                net_usd=net,
            )
        )
    return sorted(trades, key=lambda t: (t.entry_ts, t.trade_id))


def load_v2b_unit_trades(state_root: Path) -> List[Trade]:
    units = pd.read_csv(state_root / "unit_trades.csv")
    units["entry_ts"] = pd.to_datetime(units["entry_ts"], utc=True).dt.tz_convert(NY)
    units["exit_ts"] = pd.to_datetime(units["exit_ts"], utc=True).dt.tz_convert(NY)
    units["entry_price"] = pd.to_numeric(units["entry_price"], errors="coerce")
    units["exit_price"] = pd.to_numeric(units["exit_price"], errors="coerce")
    units["net_usd"] = pd.to_numeric(units["net_usd"], errors="coerce").fillna(0.0)
    out: List[Trade] = []
    for row in units.itertuples(index=False):
        out.append(
            Trade(
                trade_id=str(row.trade_id) + "_u" + str(row.unit_id),
                strategy_id=str(row.candidate),
                source="v2b",
                side=str(row.direction).lower(),
                qty=1,
                entry_ts=pd.Timestamp(row.entry_ts),
                entry_price=float(row.entry_price),
                exit_ts=pd.Timestamp(row.exit_ts),
                exit_price=float(row.exit_price),
                exit_reason=str(row.exit_reason),
                net_usd=float(row.net_usd),
            )
        )
    return out


def find_prior_opposite(v2b: Trade, st_by_day: Dict[date, List[Trade]]) -> Optional[Trade]:
    wanted = "short" if v2b.side == "long" else "long"
    candidates = [t for t in st_by_day.get(v2b.entry_ts.date(), []) if t.side == wanted and t.entry_ts < v2b.entry_ts]
    if not candidates:
        return None
    return sorted(candidates, key=lambda t: t.entry_ts)[-1]


def closed_dd(trades: Sequence[Trade]) -> float:
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for trade in sorted(trades, key=lambda t: (t.exit_ts, t.trade_id)):
        equity += trade.net_usd
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return dd


def profit_factor(trades: Sequence[Trade]) -> float:
    gross_win = sum(t.net_usd for t in trades if t.net_usd > 0)
    gross_loss = abs(sum(t.net_usd for t in trades if t.net_usd <= 0))
    return gross_win / gross_loss if gross_loss else math.inf


def summarize_closed(label: str, trades: Sequence[Trade], stress_dd: Optional[float] = None, max_open_units: int = 0) -> Summary:
    wins = sum(1 for t in trades if t.net_usd > 0)
    net = sum(t.net_usd for t in trades)
    dd = closed_dd(trades)
    return Summary(
        label=label,
        trades=len(trades),
        units=sum(max(1, t.qty) for t in trades),
        net_usd=net,
        closed_dd_usd=dd,
        stress_dd_usd=stress_dd if stress_dd is not None else dd,
        win_rate_pct=100.0 * wins / len(trades) if trades else 0.0,
        profit_factor=profit_factor(trades),
        max_open_units=max_open_units,
    )


def portfolio_stress(trades: Sequence[Trade], bars_by_day: Dict[date, pd.DataFrame], instrument: str) -> tuple[float, int]:
    point_value = POINT_VALUES[instrument]
    events_by_ts: Dict[pd.Timestamp, List[tuple[str, Trade]]] = {}
    days = set()
    for trade in trades:
        events_by_ts.setdefault(trade.entry_ts, []).append(("entry", trade))
        events_by_ts.setdefault(trade.exit_ts, []).append(("exit", trade))
        days.add(trade.entry_ts.date())
        days.add(trade.exit_ts.date())
    equity = 0.0
    peak = 0.0
    stress_dd = 0.0
    active: Dict[str, Trade] = {}
    max_open_units = 0
    for day in sorted(days):
        bars = bars_by_day.get(day)
        if bars is None or bars.empty:
            continue
        timeline = sorted(set(bars.index).union(ts for ts in events_by_ts if ts.date() == day))
        for ts in timeline:
            for kind, trade in events_by_ts.get(ts, []):
                if kind == "entry":
                    active[trade.trade_id] = trade
            if ts in bars.index:
                row = bars.loc[ts]
                stress_open = 0.0
                close_open = 0.0
                for trade in active.values():
                    if trade.side == "long":
                        close_points = float(row["close"]) - trade.entry_price
                        stress_points = float(row["low"]) - trade.entry_price
                    else:
                        close_points = trade.entry_price - float(row["close"])
                        stress_points = trade.entry_price - float(row["high"])
                    close_open += close_points * point_value * trade.qty
                    stress_open += stress_points * point_value * trade.qty
                max_open_units = max(max_open_units, sum(t.qty for t in active.values()))
                peak = max(peak, equity + close_open)
                stress_dd = min(stress_dd, equity + stress_open - peak)
            for kind, trade in events_by_ts.get(ts, []):
                if kind == "exit":
                    active.pop(trade.trade_id, None)
                    equity += trade.net_usd
                    peak = max(peak, equity)
                    stress_dd = min(stress_dd, equity - peak)
    return stress_dd, max_open_units


def v2b_state_stress(state_root: Path) -> tuple[float, int]:
    equity_path = state_root / "equity_curve.csv"
    if not equity_path.exists():
        return 0.0, 0
    equity = pd.read_csv(equity_path)
    stress = pd.to_numeric(equity.get("intrabar_stress_dd_usd"), errors="coerce").min()
    open_units = pd.to_numeric(equity.get("open_units"), errors="coerce").max()
    return float(stress if pd.notna(stress) else 0.0), int(open_units if pd.notna(open_units) else 0)


def st_summary_stress(market: str, strategy_id: str) -> tuple[float, int]:
    summary_path = REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market" / market / "summary.csv"
    if not summary_path.exists():
        return 0.0, 0
    rows = pd.read_csv(summary_path)
    row = rows[rows["strategy_id"].astype(str) == strategy_id]
    if row.empty:
        return 0.0, 0
    stress = float(pd.to_numeric(row["intrabar_stress_dd_usd"], errors="coerce").iloc[0])
    max_open = int(pd.to_numeric(row["max_open_units"], errors="coerce").iloc[0])
    return stress, max_open


def resample_15m(rth: pd.DataFrame) -> pd.DataFrame:
    return (
        rth.resample("15min", label="right", closed="right")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
        .dropna(subset=["open", "high", "low", "close"])
    )


def plot_candles(ax, df: pd.DataFrame, width_days: float) -> None:
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=1.0, alpha=0.9, zorder=3)
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
                linewidth=0.5,
                alpha=0.84,
                zorder=4,
            )
        )


def add_or_levels(ax, rth: pd.DataFrame) -> None:
    opening = rth[(rth.index.time >= time(9, 30)) & (rth.index.time < time(9, 45))]
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
        ax.axhline(value, color=color, linestyle=style, linewidth=0.85, alpha=0.65)
        ax.text(rth.index[0], value, " " + label, color=color, fontsize=7, va="bottom")


def draw_st_trade(ax, trade: Trade, prior: Optional[Trade]) -> None:
    is_prior = prior is not None and trade.trade_id == prior.trade_id
    color = "#d1495b" if trade.side == "short" else "#1b998b"
    alpha = 1.0 if is_prior else 0.32
    size = 190 if is_prior else 45
    marker = "s" if is_prior else "D"
    edge = "#111111" if is_prior else color
    ax.scatter([trade.entry_ts], [trade.entry_price], s=size, color=color, edgecolor=edge, linewidth=1.2, marker=marker, alpha=alpha, zorder=12)
    ax.scatter([trade.exit_ts], [trade.exit_price], s=max(55, size * 0.6), color=color, marker="X", edgecolor=edge, linewidth=0.9, alpha=alpha, zorder=12)
    ax.plot([trade.entry_ts, trade.exit_ts], [trade.entry_price, trade.exit_price], color=color, linewidth=1.4 if is_prior else 1.0, alpha=alpha, zorder=9)
    if is_prior:
        ax.axvline(trade.entry_ts, color=color, linewidth=1.25, alpha=0.85)
        ax.axvline(trade.exit_ts, color=color, linewidth=1.0, alpha=0.65, linestyle="--")
        stop = trade.entry_price - 25.0 if trade.side == "long" else trade.entry_price + 25.0
        target = trade.entry_price + 75.0 if trade.side == "long" else trade.entry_price - 75.0
        ax.axhline(stop, color=color, linestyle=":", linewidth=0.9, alpha=0.55)
        ax.axhline(target, color=color, linestyle=":", linewidth=0.9, alpha=0.55)
        ax.annotate(
            "ST+PMC ENTRY\n%s $%.0f" % (trade.side.upper(), trade.net_usd),
            xy=(trade.entry_ts, trade.entry_price),
            xytext=(8, 20),
            textcoords="offset points",
            color=color,
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 0.9},
            zorder=13,
        )
        ax.annotate(
            "ST+PMC EXIT",
            xy=(trade.exit_ts, trade.exit_price),
            xytext=(8, -22),
            textcoords="offset points",
            color=color,
            fontsize=8,
            weight="bold",
            arrowprops={"arrowstyle": "->", "color": color, "lw": 0.9},
            zorder=13,
        )


def draw_v2b(ax, trade: Trade, fills: pd.DataFrame) -> None:
    color = "#006dce" if trade.side == "long" else "#7b3fb2"
    marker = "^" if trade.side == "long" else "v"
    ax.scatter([trade.entry_ts], [trade.entry_price], s=120, color=color, marker=marker, zorder=10)
    ax.axvline(trade.entry_ts, color=color, linewidth=1.5, alpha=0.85)
    ax.axvline(trade.exit_ts, color=color, linewidth=1.0, alpha=0.65, linestyle="--")
    for _idx, row in fills[fills["reason"].astype(str) != "entry"].iterrows():
        reason = str(row["reason"])
        exit_marker = "o" if reason in {"tp1", "tp2"} else "x"
        ax.scatter([pd.Timestamp(row["ts"])], [float(row["price"])], s=58, color=color, marker=exit_marker, zorder=10)
    ax.annotate(
        "v2b ENTRY\n%s $%.0f" % (trade.side.upper(), trade.net_usd),
        xy=(trade.entry_ts, trade.entry_price),
        xytext=(38, -36),
        textcoords="offset points",
        color=color,
        fontsize=8,
        weight="bold",
        arrowprops={"arrowstyle": "->", "color": color, "lw": 0.9},
        zorder=13,
    )


def load_v2b_fill_groups(state_root: Path) -> Dict[str, pd.DataFrame]:
    fills = pd.read_csv(state_root / "fills.csv")
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    return {str(k): g.sort_values("ts").copy() for k, g in fills.groupby("trade_id")}


def build_charts(
    *,
    market: str,
    output_root: Path,
    v2b_trades: Sequence[Trade],
    st_by_day: Dict[date, List[Trade]],
    bars_by_day: Dict[date, pd.DataFrame],
    state_root: Path,
    hourly_context: pd.DataFrame,
    pmc_map: Dict[tuple[int, int], float],
) -> List[Dict[str, object]]:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    fill_groups = load_v2b_fill_groups(state_root)
    instrument = MARKETS[market].instrument
    rows: List[Dict[str, object]] = []
    for idx, trade in enumerate(v2b_trades, start=1):
        prior = find_prior_opposite(trade, st_by_day)
        if prior is None:
            continue
        session = trade.entry_ts.date()
        day_bars = bars_by_day.get(session)
        if day_bars is None or day_bars.empty:
            continue
        chart_start = prior.entry_ts.floor("15min")
        chart_end = pd.Timestamp.combine(session, time(16, 0)).tz_localize(NY)
        x_start = chart_start - pd.Timedelta(minutes=5)
        candles_source = day_bars[(day_bars.index >= chart_start) & (day_bars.index <= chart_end)]
        rth = _rth_bars(day_bars, session)
        candles = compute_supertrend(resample_15m(candles_source), atr_len=14, multiplier=3.0)
        candles = candles[(candles.index >= chart_start) & (candles.index <= chart_end)].copy()
        if candles.empty:
            continue
        session_st = [t for t in st_by_day.get(session, []) if t.entry_ts <= chart_end and t.exit_ts >= chart_start]
        fig, (ax, vol_ax) = plt.subplots(2, 1, figsize=(17, 9), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04})
        plot_candles(ax, candles, width_days=(15 / (24 * 60)) * 0.7)
        ctx = hourly_context[(hourly_context.index >= chart_start - pd.Timedelta(hours=1)) & (hourly_context.index <= chart_end + pd.Timedelta(hours=1))]
        if not ctx.empty:
            bull = ctx["supertrend"].where(ctx["supertrend_trend"] == 1)
            bear = ctx["supertrend"].where(ctx["supertrend_trend"] == -1)
            ax.step(ctx.index, bull, where="post", color="#008f5a", linewidth=2.1, label="Hourly ST+PMC ST bull", zorder=6)
            ax.step(ctx.index, bear, where="post", color="#d62728", linewidth=2.1, label="Hourly ST+PMC ST bear", zorder=6)
        pmc = pmc_map.get((session.year, session.month))
        if pmc is not None and np.isfinite(pmc):
            ax.axhline(float(pmc), color="#111111", linestyle="-.", linewidth=1.25, alpha=0.75, label="Prior month close")
            ax.text(chart_start, float(pmc), " PMC", color="#111111", fontsize=8, va="bottom")
        add_or_levels(ax, rth)
        for st in session_st:
            draw_st_trade(ax, st, prior)
        draw_v2b(ax, trade, fill_groups[trade.trade_id])
        ax.set_xlim(x_start, chart_end)
        ax.set_title(
            "%s combined prior-opposed ST+PMC + v2b - %s - ST %s then v2b %s - pair $%.0f"
            % (instrument, session.isoformat(), prior.side, trade.side, trade.net_usd + prior.net_usd)
        )
        ax.set_ylabel(instrument)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(15 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_xlim(x_start, chart_end)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=15, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        for label in vol_ax.get_xticklabels():
            label.set_rotation(90)
            label.set_fontsize(7)
        rel = Path("charts") / ("%03d_%s_%s_%s.png" % (idx, session.isoformat(), trade.side, "win" if trade.net_usd + prior.net_usd > 0 else "loss"))
        out = output_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": session.isoformat(),
                "side": trade.side,
                "v2b_net": trade.net_usd,
                "prior_st_net": prior.net_usd,
                "pair_net": trade.net_usd + prior.net_usd,
                "v2b_trade_id": trade.trade_id,
                "prior_st_trade_id": prior.trade_id,
                "prior_st_side": prior.side,
                "chart_start": chart_start.isoformat(),
                "chart_end": chart_end.isoformat(),
                "chart": str(rel),
            }
        )
        if idx % 50 == 0:
            print("  %s charted %d/%d" % (instrument, idx, len(v2b_trades)), flush=True)
    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# %s Combined Prior-Opposed ST+PMC + v2b Charts" % instrument,
        "",
        "Each chart starts at the causal prior ST+PMC entry and runs through the RTH close, with every available 15-minute candle in between shown.",
        "",
        "Large square/X = prior opposite ST+PMC entry/exit; diamonds = other same-session ST+PMC trades; triangle/circles/x markers = gated v2b entry/exits. The thick stepped line is the hourly Supertrend used by ST+PMC, and the black dash-dot line is prior month close.",
        "",
        "| # | Session | Side | v2b Net | Prior ST Net | Pair Net | Chart |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${v2b_net:,.2f} | ${prior_st_net:,.2f} | ${pair_net:,.2f} | [{chart}]({chart}) |".format(**row)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines))
    return rows


def write_market_report(
    *,
    market: str,
    output_root: Path,
    summaries: Sequence[Summary],
    pair_rows: Sequence[Dict[str, object]],
    charts_root: Path,
    st_strategy_id: str,
    state_root: Path,
) -> None:
    instrument = MARKETS[market].instrument
    with (output_root / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "market",
                "instrument",
                "label",
                "trades",
                "units",
                "net_usd",
                "closed_dd_usd",
                "stress_dd_usd",
                "win_rate_pct",
                "profit_factor",
                "max_open_units",
                "net_over_stress",
            ],
        )
        writer.writeheader()
        for s in summaries:
            writer.writerow(
                {
                    "market": market,
                    "instrument": instrument,
                    "label": s.label,
                    "trades": s.trades,
                    "units": s.units,
                    "net_usd": "%.2f" % s.net_usd,
                    "closed_dd_usd": "%.2f" % s.closed_dd_usd,
                    "stress_dd_usd": "%.2f" % s.stress_dd_usd,
                    "win_rate_pct": "%.2f" % s.win_rate_pct,
                    "profit_factor": "%.4f" % s.profit_factor,
                    "max_open_units": s.max_open_units,
                    "net_over_stress": "%.2f" % s.net_over_stress,
                }
            )
    pair_df = pd.DataFrame(pair_rows)
    if not pair_df.empty:
        pair_df.to_csv(output_root / "paired_trade_contribution.csv", index=False)
    lines = [
        "# %s Prior-Opposed ST+PMC + v2b Combined System" % instrument,
        "",
        "This is a combined-system audit for the prior-opposed branch. It keeps four views separate:",
        "",
        "- `v2b gated only`: actual broker-like v2b `S_1_1_3` fills after prior opposite ST+PMC.",
        "- `prior ST only`: only the specific ST+PMC trades that gated a later v2b campaign.",
        "- `paired prior ST + v2b`: the causal ST+PMC gate trade plus its paired v2b campaign.",
        "- `full ST + gated v2b portfolio`: all `%s` ST+PMC trades plus the gated v2b campaign tape." % st_strategy_id,
        "",
        "| View | Trades | Units | Net | Closed DD | Stress DD | Win % | PF | Max Open Units | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        lines.append(
            "| %s | %d | %d | %s | %s | %s | %.2f | %.3f | %d | %.2f |"
            % (
                s.label,
                s.trades,
                s.units,
                money(s.net_usd),
                money(s.closed_dd_usd),
                money(s.stress_dd_usd),
                s.win_rate_pct,
                s.profit_factor,
                s.max_open_units,
                s.net_over_stress,
            )
        )
    lines += [
        "",
        "Read:",
        "",
        "- The paired view answers whether the required prior ST+PMC trade adds or subtracts value around the v2b setup.",
        "- The full portfolio view is the closer deployment proxy if ST+PMC runs continuously and v2b is added only after the prior-opposite condition.",
        "- Stress for combined views is conservative: standalone v2b stress plus the relevant ST+PMC stress/closed-DD budget, so overlap risk is not hidden in this exploratory pass.",
        "",
        "Files:",
        "",
        "- `summary.csv`",
        "- `paired_trade_contribution.csv`",
        "- `states/%s/`" % state_root.name,
        "- [`charts/combined_15m/INDEX.md`](charts/combined_15m/INDEX.md)",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines))


def build_market(market: str, output_root: Path, *, force_v2b: bool, force_charts: bool) -> List[Summary]:
    cfg = MARKETS[market]
    market_root = output_root / market
    market_root.mkdir(parents=True, exist_ok=True)
    state_root = run_gated_v2b(market, output_root, force=force_v2b)
    st_strategy_id = "%s_hourly_st_pmc_sl25_tp75_3r" % market
    st_trades = load_st_trades(market, st_strategy_id)
    v2b_trades = load_v2b_trades(state_root, market)
    v2b_units = load_v2b_unit_trades(state_root)

    st_by_day: Dict[date, List[Trade]] = {}
    for trade in st_trades:
        st_by_day.setdefault(trade.entry_ts.date(), []).append(trade)
    pair_rows = []
    prior_trades_by_id: Dict[str, Trade] = {}
    pair_trades: List[Trade] = []
    for v2b in v2b_trades:
        prior = find_prior_opposite(v2b, st_by_day)
        if prior is None:
            continue
        prior_trades_by_id[prior.trade_id] = prior
        pair_trades.append(
            Trade(
                trade_id="pair_" + v2b.trade_id,
                strategy_id="combined_pair",
                source="pair",
                side=v2b.side,
                qty=v2b.qty + prior.qty,
                entry_ts=prior.entry_ts,
                entry_price=prior.entry_price,
                exit_ts=max(v2b.exit_ts, prior.exit_ts),
                exit_price=v2b.exit_price,
                exit_reason="paired",
                net_usd=v2b.net_usd + prior.net_usd,
            )
        )
        pair_rows.append(
            {
                "session": v2b.entry_ts.date().isoformat(),
                "v2b_trade_id": v2b.trade_id,
                "v2b_side": v2b.side,
                "v2b_entry_ts": v2b.entry_ts.isoformat(),
                "v2b_exit_ts": v2b.exit_ts.isoformat(),
                "v2b_net_usd": v2b.net_usd,
                "prior_st_trade_id": prior.trade_id,
                "prior_st_side": prior.side,
                "prior_st_entry_ts": prior.entry_ts.isoformat(),
                "prior_st_exit_ts": prior.exit_ts.isoformat(),
                "prior_st_net_usd": prior.net_usd,
                "pair_net_usd": v2b.net_usd + prior.net_usd,
            }
        )

    prior_trades = sorted(prior_trades_by_id.values(), key=lambda t: (t.entry_ts, t.trade_id))
    start_dt = min([t.entry_ts for t in v2b_trades], default=pd.Timestamp("2100-01-01", tz=NY))
    end_dt = max([t.exit_ts for t in v2b_trades], default=pd.Timestamp("1900-01-01", tz=NY))
    st_full = [t for t in st_trades if start_dt.date() <= t.entry_ts.date() <= end_dt.date()]
    v2b_stress, v2b_max_open = v2b_state_stress(state_root)
    full_st_stress, full_st_max_open = st_summary_stress(market, st_strategy_id)
    prior_st_summary = summarize_closed("prior ST only", prior_trades, None, 1 if prior_trades else 0)
    prior_st_stress = prior_st_summary.closed_dd_usd
    prior_st_max_open = prior_st_summary.max_open_units
    # Combined stress is intentionally conservative here: add the standalone
    # stress budgets. It avoids hiding overlap risk without requiring a slow
    # full portfolio tick-by-tick recomputation for this exploratory pass.
    pair_stress = v2b_stress + min(0.0, prior_st_stress)
    pair_max_open = v2b_max_open + prior_st_max_open
    full_stress = v2b_stress + min(0.0, full_st_stress)
    full_max_open = v2b_max_open + full_st_max_open

    summaries = [
        summarize_closed("v2b gated only", v2b_trades, v2b_stress, v2b_max_open),
        prior_st_summary,
        summarize_closed("paired prior ST + v2b", pair_trades, pair_stress, pair_max_open),
        summarize_closed("full ST + gated v2b portfolio", st_full + v2b_trades, full_stress, full_max_open),
    ]
    charts_root = market_root / "charts" / "combined_15m"
    if force_charts or not (charts_root / "INDEX.md").exists():
        print("Loading %s 1m bars for charts..." % cfg.instrument, flush=True)
        raw = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
        bars_by_day = {d: raw.get(d) for d in sorted({t.entry_ts.date() for t in v2b_trades})}
        hourly_context = compute_supertrend(resample_hourly(concat_all_1m(raw)), atr_len=14, multiplier=3.0)
        pmc_map = load_prev_month_close_map(cfg.daily_path)
        chart_rows = build_charts(
            market=market,
            output_root=charts_root,
            v2b_trades=v2b_trades,
            st_by_day=st_by_day,
            bars_by_day=bars_by_day,
            state_root=state_root,
            hourly_context=hourly_context,
            pmc_map=pmc_map,
        )
    else:
        chart_rows = []
    write_market_report(
        market=market,
        output_root=market_root,
        summaries=summaries,
        pair_rows=pair_rows,
        charts_root=charts_root,
        st_strategy_id=st_strategy_id,
        state_root=state_root,
    )
    print("Wrote %s" % (market_root / "INDEX.md"), flush=True)
    return summaries


def write_root(output_root: Path, all_rows: Dict[str, List[Summary]]) -> None:
    lines = [
        "# Prior-Opposed ST+PMC + v2b Combined System",
        "",
        "Combined-system audit for MNQ and NQ. The gated v2b leg is the same `S_1_1_3` prior-opposed rule; ST+PMC is the same-market `sl25_tp75_3r` candidate.",
        "",
        "| Market | View | Trades | Net | Stress DD | Max Open Units | PF | Net/Stress |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for market, summaries in all_rows.items():
        for s in summaries:
            lines.append(
                "| %s | %s | %d | %s | %s | %d | %.3f | %.2f |"
                % (MARKETS[market].instrument, s.label, s.trades, money(s.net_usd), money(s.stress_dd_usd), s.max_open_units, s.profit_factor, s.net_over_stress)
            )
    lines += [
        "",
        "Market reports:",
        "",
        "- [MNQ](mnq/INDEX.md)",
        "- [NQ](nq/INDEX.md)",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build combined prior-opposed ST+PMC + v2b study for MNQ/NQ.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/v2b_prior_opposed_stpmc_combined_system")
    parser.add_argument("--markets", nargs="+", default=["mnq", "nq"], choices=["mnq", "nq"])
    parser.add_argument("--force-v2b", action="store_true")
    parser.add_argument("--no-force-charts", action="store_true")
    args = parser.parse_args(argv)
    args.output_root.mkdir(parents=True, exist_ok=True)
    all_rows: Dict[str, List[Summary]] = {}
    for market in args.markets:
        all_rows[market] = build_market(
            market,
            args.output_root,
            force_v2b=args.force_v2b,
            force_charts=not args.no_force_charts,
        )
        write_root(args.output_root, all_rows)
    write_root(args.output_root, all_rows)
    print("Wrote %s" % (args.output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
