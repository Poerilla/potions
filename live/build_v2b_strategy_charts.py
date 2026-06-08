from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

from .models import Bar
from .strategies.atr_supertrend_dca import _supertrend


REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
V2D = MNQ_ROOT / "v2d"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"
DEFAULT_DBN = MNQ_ROOT / "raw" / "extracted_new" / "glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst"
DEFAULT_STATE_ROOT = REPO / "live" / "state" / "v2b_strategy_plugin_replay" / "states" / "mnq_v2b_scaleout_oco_then_reverse"
DEFAULT_OUT_ROOT = REPO / "live" / "state" / "v2b_strategy_plugin_replay" / "charts" / "oco_then_reverse"

REALISM_CAPTION = (
    "Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, "
    "stop gap-through ON, stop-first same-bar, OCO-collapsed risk."
)

DBN_BY_MARKET: Dict[str, Path] = {
    "mnq": REPO / "mnq" / "raw" / "extracted_new" / "glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst",
    "nq": REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst",
    "ym": REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    "mym": REPO / "mym" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
    "es": REPO / "es" / "raw" / "glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst",
    "mes": REPO / "mes" / "mes_1min_raw.csv",
}

sys.path[:0] = [str(MNQ_ROOT), str(SCRIPTS), str(V2D), str(CASE)]

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass(frozen=True)
class Fill:
    ts: pd.Timestamp
    side: str
    quantity: int
    price: float
    reason: str
    trade_id: str

    @property
    def day(self) -> date:
        return self.ts.date()


@dataclass(frozen=True)
class UnitTrade:
    trade_id: str
    direction: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    exit_reason: str
    net_usd: float

    @property
    def day(self) -> date:
        return self.entry_ts.date()


@dataclass(frozen=True)
class SessionSummary:
    day: date
    net_usd: float
    units: int
    trades: int
    label: str


def build_charts(
    *,
    state_root: Path = DEFAULT_STATE_ROOT,
    dbn: Optional[Path] = DEFAULT_DBN,
    market: Optional[str] = None,
    out_root: Path = DEFAULT_OUT_ROOT,
    max_winners: int = 50,
    max_losers: int = 50,
    all_days: bool = False,
    st_minutes: int = 3,
    st_atr_len: int = 14,
    st_atr_mult: float = 3.0,
) -> List[Path]:
    out_root.mkdir(parents=True, exist_ok=True)
    instrument, inferred_market = _read_instance_identity(state_root / "strategy_instances.csv")
    market = (market or inferred_market or instrument).lower()
    dbn = dbn or DBN_BY_MARKET.get(market)
    if dbn is None:
        raise ValueError("No DBN path for market %s" % market)
    fills = _read_fills(state_root / "fills.csv")
    unit_trades = _read_unit_trades(state_root / "unit_trades.csv")
    equity = _read_csv(state_root / "equity_curve.csv")
    session_rows = _session_summaries(unit_trades)
    selected = _select_sessions(session_rows, max_winners=max_winners, max_losers=max_losers, all_days=all_days)

    print("Loading %s 1m data for V2B charts..." % instrument, flush=True)
    gby = _load_1m_by_ny_date_any(dbn.resolve(), market)

    built: List[Path] = []
    built.append(_plot_equity_overview(out_root / "equity_overview.png", equity, session_rows, instrument))

    fills_by_day: Dict[date, List[Fill]] = {}
    for fill in fills:
        fills_by_day.setdefault(fill.day, []).append(fill)
    units_by_day: Dict[date, List[UnitTrade]] = {}
    for unit in unit_trades:
        units_by_day.setdefault(unit.day, []).append(unit)

    for summary in selected:
        raw = gby.get(summary.day)
        if raw is None or raw.empty:
            continue
        rth = _rth_bars(raw, summary.day)
        if rth.empty:
            continue
        bucket = "winners" if summary.net_usd > 0 else "losers" if summary.net_usd < 0 else "flat"
        out = out_root / bucket / f"{summary.day.isoformat()}_{_slug(summary.label)}.png"
        _plot_session(
            out,
            rth,
            fills_by_day.get(summary.day, []),
            units_by_day.get(summary.day, []),
            summary,
            instrument,
            st_minutes=st_minutes,
            st_atr_len=st_atr_len,
            st_atr_mult=st_atr_mult,
        )
        built.append(out)

    _write_index(
        out_root,
        session_rows,
        selected,
        built,
        st_minutes=st_minutes,
        st_atr_len=st_atr_len,
        st_atr_mult=st_atr_mult,
    )
    return built


def _rth_bars(df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[
        df.index.map(
            lambda ts: ts.date() == session_day
            and ts.time() >= pd.Timestamp("09:30").time()
            and ts.time() < pd.Timestamp("16:00").time()
        )
    ].sort_index()


def _load_1m_by_ny_date_any(path: Path, market: str) -> Dict[date, pd.DataFrame]:
    if path.suffix.lower() != ".csv":
        return mdata.load_1m_by_ny_date(path, market)
    inst = market.lower()
    print("Loading CSV %s (%s) ..." % (path, inst.upper()), flush=True)
    df = pd.read_csv(path, parse_dates=["ts_event"])
    df = df[~df["symbol"].astype(str).str.contains("-", na=False)]
    df = df[mdata._symbol_mask(df["symbol"].astype(str), inst)].copy()
    if df.empty:
        return {}
    if df["ts_event"].dt.tz is None:
        df["ts_event"] = df["ts_event"].dt.tz_localize("UTC")
    df["ts_event"] = df["ts_event"].dt.tz_convert(mdata.NY)
    df["d"] = df["ts_event"].dt.date
    fm = (
        df.groupby(["d", "symbol"])["volume"]
        .sum()
        .groupby(level="d")
        .idxmax()
        .apply(lambda x: x[1])
        .to_dict()
    )
    df = df[df.apply(lambda row: row["symbol"] == fm.get(row["d"]), axis=1)]
    df = df.set_index("ts_event").sort_index()
    gby = {d: g.drop(columns=["d"], errors="ignore") for d, g in df.groupby(df.index.date)}
    print("  %s NY dates with bars" % f"{len(gby):,}", flush=True)
    return gby


def _session_summaries(units: Sequence[UnitTrade]) -> List[SessionSummary]:
    by_day: Dict[date, List[UnitTrade]] = {}
    for unit in units:
        by_day.setdefault(unit.day, []).append(unit)
    out: List[SessionSummary] = []
    for day, rows in sorted(by_day.items()):
        trades = len({row.trade_id for row in rows})
        net = sum(row.net_usd for row in rows)
        if net > 0:
            label = "win"
        elif net < 0:
            label = "loss"
        else:
            label = "flat"
        out.append(SessionSummary(day=day, net_usd=net, units=len(rows), trades=trades, label=label))
    return out


def _select_sessions(
    rows: Sequence[SessionSummary],
    *,
    max_winners: int,
    max_losers: int,
    all_days: bool,
) -> List[SessionSummary]:
    if all_days:
        return list(rows)
    winners = sorted([row for row in rows if row.net_usd > 0], key=lambda row: row.net_usd, reverse=True)[:max_winners]
    losers = sorted([row for row in rows if row.net_usd < 0], key=lambda row: row.net_usd)[:max_losers]
    selected = {row.day: row for row in winners + losers}
    return [selected[day] for day in sorted(selected)]


def _plot_equity_overview(out: Path, equity_rows: List[Dict[str, str]], sessions: Sequence[SessionSummary], instrument: str) -> Path:
    rows = [row for row in equity_rows if row.get("ts")]
    xs = [pd.Timestamp(row["ts"]) for row in rows]
    close_eq = [float(row.get("close_equity_usd") or 0.0) for row in rows]
    stress_eq = [float(row.get("intrabar_stress_equity_usd") or 0.0) for row in rows]
    dd = [float(row.get("intrabar_stress_dd_usd") or 0.0) for row in rows]
    fig, (ax, dd_ax) = plt.subplots(2, 1, figsize=(15, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax.plot(xs, close_eq, color="#0891b2", linewidth=1.5, label="Close equity")
    ax.plot(xs, stress_eq, color="#f97316", linewidth=0.8, alpha=0.65, label="Intrabar stress equity")
    ax.set_title(
        f"{instrument} v2b StrategyPlugin OCO then reverse - equity overview\n"
        f"sessions {len(sessions)}, net ${close_eq[-1]:,.0f}, max stress DD ${min(dd):,.0f}"
        if close_eq and dd
        else f"{instrument} v2b StrategyPlugin OCO then reverse - equity overview"
    )
    ax.set_ylabel("Equity USD")
    ax.grid(True, alpha=0.18)
    ax.legend(loc="upper left", fontsize=8)
    dd_ax.fill_between(xs, dd, 0, color="#ef4444", alpha=0.35)
    dd_ax.set_ylabel("Stress DD")
    dd_ax.grid(True, alpha=0.18)
    dd_ax.xaxis.set_major_locator(mdates.YearLocator())
    dd_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def _plot_session(
    out: Path,
    bars: pd.DataFrame,
    fills: Sequence[Fill],
    units: Sequence[UnitTrade],
    summary: SessionSummary,
    instrument: str,
    *,
    st_minutes: int,
    st_atr_len: int,
    st_atr_mult: float,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 7))
    x_map = _plot_candles(ax, bars)
    _plot_or_levels(ax, bars)
    _plot_intraday_supertrend(
        ax,
        bars,
        x_map,
        tf_minutes=st_minutes,
        atr_len=st_atr_len,
        atr_mult=st_atr_mult,
    )
    _plot_fills(ax, x_map, fills)
    net = sum(unit.net_usd for unit in units)
    exits = ", ".join(sorted({unit.exit_ts.strftime("%H:%M") + " " + unit.exit_reason for unit in units}))[:110]
    ax.set_title(
        f"{instrument} v2b StrategyPlugin OCO then reverse - {summary.day.isoformat()} - {summary.label}\n"
        f"net ${net:,.2f}, unit exits {summary.units}, trade campaigns {summary.trades}; exits: {exits}"
    )
    ax.set_ylabel(instrument)
    ax.grid(True, alpha=0.18)
    ax.legend(loc="upper left", fontsize=8)
    _format_intraday_axis(ax, bars)
    fig.tight_layout()
    fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_candles(ax, bars: pd.DataFrame) -> Dict[pd.Timestamp, float]:
    xs = list(range(len(bars)))
    x_map = {pd.Timestamp(ts): float(i) for i, ts in enumerate(bars.index)}
    width = 0.58
    for i, (_, row) in enumerate(bars.iterrows()):
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        color = "#059669" if c >= o else "#dc2626"
        ax.vlines(i, l, h, color=color, linewidth=0.7, alpha=0.9)
        body_low = min(o, c)
        body_height = max(abs(c - o), 0.25)
        ax.add_patch(
            Rectangle(
                (i - width / 2, body_low),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.75,
            )
        )
    ax.set_xlim(-2, len(xs) + 2)
    return x_map


def _plot_or_levels(ax, bars: pd.DataFrame) -> None:
    or_bars = bars.iloc[:15]
    if len(or_bars) < 15:
        return
    rh = float(or_bars["high"].max())
    rl = float(or_bars["low"].min())
    rv = rh - rl
    long_entry = rh + 0.25
    short_entry = rl - 0.25
    ax.axvspan(-0.5, 14.5, color="#facc15", alpha=0.14, label="09:30-09:45 OR")
    ax.axhline(rh, color="#2563eb", linewidth=1.3, label="OR high")
    ax.axhline(rl, color="#7c3aed", linewidth=1.3, label="OR low")
    ax.axhline(long_entry, color="#16a34a", linestyle="--", linewidth=1.0, label="Long stop")
    ax.axhline(short_entry, color="#dc2626", linestyle="--", linewidth=1.0, label="Short stop")
    ax.axhline(rh + rv, color="#16a34a", linestyle=":", linewidth=0.9, label="Long TP1")
    ax.axhline(rh + 2 * rv, color="#15803d", linestyle=":", linewidth=0.9, label="Long TP2")
    ax.axhline(rl - rv, color="#dc2626", linestyle=":", linewidth=0.9, label="Short TP1")
    ax.axhline(rl - 2 * rv, color="#991b1b", linestyle=":", linewidth=0.9, label="Short TP2")


def _plot_intraday_supertrend(
    ax,
    bars: pd.DataFrame,
    x_map: Dict[pd.Timestamp, float],
    *,
    tf_minutes: int,
    atr_len: int,
    atr_mult: float,
) -> None:
    if bars.empty:
        return
    rule = f"{int(tf_minutes)}min"
    bars_tf = (
        bars[["open", "high", "low", "close"]]
        .resample(rule, label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    if bars_tf.empty:
        return
    st_bars = [
        Bar(
            instrument="",
            timeframe=f"{int(tf_minutes)}m",
            ts=pd.Timestamp(ts).isoformat(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=0.0,
            complete=True,
            source=f"intraday_{int(tf_minutes)}m_resample",
        )
        for ts, row in bars_tf.iterrows()
    ]
    points = _supertrend(st_bars, atr_len, atr_mult)
    if not points:
        return

    first_bull = True
    first_bear = True
    for bullish in (True, False):
        xs: List[float] = []
        ys: List[float] = []
        for p in points:
            if p.bullish != bullish:
                if xs:
                    label = (
                        f"{int(tf_minutes)}m ATR ST bullish"
                        if bullish and first_bull
                        else f"{int(tf_minutes)}m ATR ST bearish"
                        if (not bullish and first_bear)
                        else None
                    )
                    ax.plot(xs, ys, color="#14b8a6" if bullish else "#f97316", linewidth=1.2, alpha=0.95, label=label)
                    first_bull = first_bull and not bullish
                    first_bear = first_bear and bullish
                    xs = []
                    ys = []
                continue
            x = _nearest_x(x_map, pd.Timestamp(p.ts))
            if x is None:
                continue
            xs.append(x)
            ys.append(float(p.stop))
        if xs:
            label = (
                f"{int(tf_minutes)}m ATR ST bullish"
                if bullish and first_bull
                else f"{int(tf_minutes)}m ATR ST bearish"
                if (not bullish and first_bear)
                else None
            )
            ax.plot(xs, ys, color="#14b8a6" if bullish else "#f97316", linewidth=1.2, alpha=0.95, label=label)


def _plot_fills(ax, x_map: Dict[pd.Timestamp, float], fills: Sequence[Fill]) -> None:
    seen_labels = set()
    for fill in sorted(fills, key=lambda item: item.ts):
        x = _nearest_x(x_map, fill.ts)
        if x is None:
            continue
        is_entry = fill.reason == "entry"
        is_buy = fill.side == "buy"
        if is_entry and is_buy:
            marker, color, label = "^", "#16a34a", "Long entry"
        elif is_entry:
            marker, color, label = "v", "#dc2626", "Short entry"
        elif is_buy:
            marker, color, label = "o", "#2563eb", "Buy exit"
        else:
            marker, color, label = "o", "#f97316", "Sell exit"
        ax.scatter([x], [fill.price], marker=marker, s=46 if is_entry else 32, color=color, zorder=5, label=None if label in seen_labels else label)
        seen_labels.add(label)
        text = f"{fill.ts.strftime('%H:%M')} {fill.reason} x{fill.quantity}"
        ax.annotate(
            text,
            xy=(x, fill.price),
            xytext=(4, 6 if is_buy else -12),
            textcoords="offset points",
            fontsize=6,
            color="#111827",
            alpha=0.85,
        )


def _nearest_x(x_map: Dict[pd.Timestamp, float], ts: pd.Timestamp) -> Optional[float]:
    if ts in x_map:
        return x_map[ts]
    target = ts.tz_convert(None) if ts.tzinfo else ts
    for key, value in x_map.items():
        key_cmp = key.tz_convert(None) if key.tzinfo else key
        if key_cmp == target:
            return value
    return None


def _format_intraday_axis(ax, bars: pd.DataFrame) -> None:
    ticks = []
    labels = []
    for i, ts in enumerate(bars.index):
        t = pd.Timestamp(ts)
        if t.minute == 0 or (t.hour == 9 and t.minute == 30):
            ticks.append(i)
            labels.append(t.strftime("%H:%M"))
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right")


def _write_index(
    out_root: Path,
    sessions: Sequence[SessionSummary],
    selected: Sequence[SessionSummary],
    built: Sequence[Path],
    *,
    st_minutes: int,
    st_atr_len: int,
    st_atr_mult: float,
) -> None:
    winners = sorted([row for row in sessions if row.net_usd > 0], key=lambda row: row.net_usd, reverse=True)
    losers = sorted([row for row in sessions if row.net_usd < 0], key=lambda row: row.net_usd)
    lines = [
        "# V2B StrategyPlugin OCO Then Reverse Charts",
        "",
        "Charts use the hardened intraday `StrategyPlugin` fills, not the old long-priority scanner rows.",
        "",
        f"> {REALISM_CAPTION}",
        "",
        f"Overlay: {int(st_minutes)}m ATR Supertrend (len={st_atr_len}, mult={st_atr_mult:.2f}) from intraday RTH bars.",
        "",
        f"- Sessions with unit exits: {len(sessions)}",
        f"- Selected session charts: {len([path for path in built if path.name != 'equity_overview.png'])}",
        f"- Total selected net: ${sum(row.net_usd for row in selected):,.2f}",
        "",
        "## Overview",
        "",
        "- [equity_overview.png](equity_overview.png)",
        "",
        "## Best Winning Sessions",
        "",
        "| Date | Net | Units | Trades | Chart |",
        "|---|---:|---:|---:|---|",
    ]
    for row in winners[:50]:
        path = Path("winners") / f"{row.day.isoformat()}_{_slug(row.label)}.png"
        if (out_root / path).exists():
            lines.append(f"| {row.day.isoformat()} | ${row.net_usd:,.2f} | {row.units} | {row.trades} | [{path.name}]({path.as_posix()}) |")
    lines.extend(["", "## Worst Losing Sessions", "", "| Date | Net | Units | Trades | Chart |", "|---|---:|---:|---:|---|"])
    for row in losers[:50]:
        path = Path("losers") / f"{row.day.isoformat()}_{_slug(row.label)}.png"
        if (out_root / path).exists():
            lines.append(f"| {row.day.isoformat()} | ${row.net_usd:,.2f} | {row.units} | {row.trades} | [{path.name}]({path.as_posix()}) |")
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_fills(path: Path) -> List[Fill]:
    rows = _read_csv(path)
    out: List[Fill] = []
    for row in rows:
        out.append(
            Fill(
                ts=pd.Timestamp(row["ts"]),
                side=row["side"].lower(),
                quantity=int(float(row["quantity"])),
                price=float(row["price"]),
                reason=row["reason"],
                trade_id=row["trade_id"],
            )
        )
    return out


def _read_unit_trades(path: Path) -> List[UnitTrade]:
    rows = _read_csv(path)
    out: List[UnitTrade] = []
    for row in rows:
        out.append(
            UnitTrade(
                trade_id=row["trade_id"],
                direction=row["direction"],
                entry_ts=pd.Timestamp(row["entry_ts"]),
                exit_ts=pd.Timestamp(row["exit_ts"]),
                exit_reason=row["exit_reason"],
                net_usd=float(row["net_usd"]),
            )
        )
    return out


def _read_instance_identity(path: Path) -> tuple[str, str]:
    rows = _read_csv(path)
    if not rows:
        return "MNQ", "mnq"
    row = rows[0]
    instrument = str(row.get("instrument") or "MNQ").upper()
    market = instrument.lower()
    try:
        config = json.loads(row.get("config_json") or "{}")
        market = str(config.get("market") or market).lower()
    except json.JSONDecodeError:
        pass
    return instrument, market


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build charts for the hardened MNQ v2b StrategyPlugin replay.")
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--dbn", type=Path, default=None)
    parser.add_argument("--market", type=str, default=None)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--max-winners", type=int, default=50)
    parser.add_argument("--max-losers", type=int, default=50)
    parser.add_argument("--all-days", action="store_true")
    parser.add_argument("--st-minutes", type=int, default=3)
    parser.add_argument("--st-atr-len", type=int, default=14)
    parser.add_argument("--st-atr-mult", type=float, default=3.0)
    args = parser.parse_args()
    built = build_charts(
        state_root=args.state_root,
        dbn=args.dbn,
        market=args.market,
        out_root=args.out_root,
        max_winners=args.max_winners,
        max_losers=args.max_losers,
        all_days=args.all_days,
        st_minutes=args.st_minutes,
        st_atr_len=args.st_atr_len,
        st_atr_mult=args.st_atr_mult,
    )
    print("Wrote %d chart artifacts under %s" % (len(built), args.out_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
