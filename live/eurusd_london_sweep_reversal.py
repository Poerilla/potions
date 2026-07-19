"""EURUSD London killzone sweep → reverse at the opposite level (scaleout 1/1/1).

Rules (America/New_York):
- London high/low form in the **02:00–05:00** killzone.
- After the killzone completes (**05:00**), watch for the first sweep:
  - London **low taken** first → long bias; buy stop through London high,
    initial stop at London low.
  - London **high taken** first → short bias; sell stop through London low,
    initial stop at London high.
- **3 units**:
  - Unit 1 → **1R**
  - Unit 2 → **2R**
  - Unit 3 → **3R**
  - After unit 1 hits TP, remaining stop moves to **breakeven** (active next bar).
- Still open at **16:00** → flatten remainder at close.
- One campaign max per session. Same-bar dual sweep skips the day.

Charts: ~100 evenly sampled trades, 5m candles from 02:00 → 16:00 NY.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_prior_opposed_5m_charts import _resample_5m, _select_trades
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .nq_v2b_prior_opposed_15m_charts import FillTrade, _plot_candles


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0
UNITS = 3  # 1 @ 1R, 1 @ 2R, 1 @ 3R

KZ_START = time(2, 0)
KZ_END = time(5, 0)
TRADE_START = time(5, 0)
NY_CLOSE = time(16, 0)


@dataclass
class UnitExit:
    unit: int
    ts: str
    price: float
    reason: str
    pl: float


@dataclass
class LondonSweepTrade:
    session: str
    side: str
    london_high: float
    london_low: float
    sweep_ts: str
    entry_ts: str
    entry_price: float
    initial_stop: float
    tp1: float
    tp2: float
    tp3: float
    exit_ts: str
    exit_price: float
    exit_reason: str
    net_usd: float
    r_mult: float
    exits_json: str = ""
    exits: List[UnitExit] = field(default_factory=list, repr=False)


def _ts(session: date, t: time) -> pd.Timestamp:
    return pd.Timestamp(NY_TZ.localize(datetime.combine(session, t)))


def _session_frame(bars_by_day: Dict[date, pd.DataFrame], session: date) -> pd.DataFrame:
    frames = []
    prev = bars_by_day.get(session - timedelta(days=1))
    if prev is not None and not prev.empty:
        frames.append(prev)
    cur = bars_by_day.get(session)
    if cur is not None and not cur.empty:
        frames.append(cur)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames).sort_index()
    return merged[~merged.index.duplicated(keep="last")]


def _london_range(df: pd.DataFrame, session: date) -> Optional[Tuple[float, float]]:
    kz0, kz1 = _ts(session, KZ_START), _ts(session, KZ_END)
    kz = df[(df.index >= kz0) & (df.index < kz1)]
    if kz.empty:
        return None
    hi = float(kz["high"].max())
    lo = float(kz["low"].min())
    if hi <= lo:
        return None
    return hi, lo


def _unit_pl(side: str, entry: float, exit_px: float) -> float:
    pts = exit_px - entry if side == "long" else entry - exit_px
    return pts * POINT_VALUE - FEE_PER_UNIT


def _finalize(
    *,
    session: date,
    side: str,
    london_high: float,
    london_low: float,
    risk: float,
    sweep_ts: pd.Timestamp,
    entry_ts: pd.Timestamp,
    entry_px: float,
    initial_stop: float,
    tp1: float,
    tp2: float,
    tp3: float,
    exits: List[UnitExit],
) -> LondonSweepTrade:
    net = sum(ex.pl for ex in exits)
    last = exits[-1]
    avg_r = (net / (risk * POINT_VALUE)) if risk > 0 else 0.0
    reasons = sorted({ex.reason for ex in exits})
    return LondonSweepTrade(
        session=session.isoformat(),
        side=side,
        london_high=london_high,
        london_low=london_low,
        sweep_ts=sweep_ts.isoformat(),
        entry_ts=entry_ts.isoformat(),
        entry_price=entry_px,
        initial_stop=initial_stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        exit_ts=last.ts,
        exit_price=last.price,
        exit_reason="+".join(reasons),
        net_usd=net,
        r_mult=avg_r,
        exits_json=json.dumps([asdict(ex) for ex in exits]),
        exits=exits,
    )


def _simulate_day(df: pd.DataFrame, session: date) -> Optional[LondonSweepTrade]:
    rng = _london_range(df, session)
    if rng is None:
        return None
    london_high, london_low = rng
    risk = london_high - london_low
    trade_start = _ts(session, TRADE_START)
    ny_close = _ts(session, NY_CLOSE)
    window = df[(df.index >= trade_start) & (df.index < ny_close)]
    if window.empty:
        return None

    bias = ""
    sweep_ts: Optional[pd.Timestamp] = None
    entry_ts: Optional[pd.Timestamp] = None
    entry_px = 0.0
    initial_stop = 0.0
    stop_px = 0.0
    tp1 = tp2 = tp3 = 0.0
    side = ""
    remaining = {1, 2, 3}
    be_armed = False
    pending_be = False  # arm BE on the bar after TP1 fills
    exits: List[UnitExit] = []

    for ts, bar in window.iterrows():
        h = float(bar["high"])
        l = float(bar["low"])
        stamp = pd.Timestamp(ts)

        if not bias:
            low_taken = l <= london_low
            high_taken = h >= london_high
            if low_taken and high_taken:
                return None
            if low_taken:
                bias = "long"
                sweep_ts = stamp
            elif high_taken:
                bias = "short"
                sweep_ts = stamp
            continue

        if entry_ts is None:
            if bias == "long" and h >= london_high:
                side = "long"
                entry_ts = stamp
                entry_px = london_high
                initial_stop = stop_px = london_low
                tp1 = entry_px + risk
                tp2 = entry_px + 2 * risk
                tp3 = entry_px + 3 * risk
            elif bias == "short" and l <= london_low:
                side = "short"
                entry_ts = stamp
                entry_px = london_low
                initial_stop = stop_px = london_high
                tp1 = entry_px - risk
                tp2 = entry_px - 2 * risk
                tp3 = entry_px - 3 * risk
            else:
                continue

        assert sweep_ts is not None and entry_ts is not None

        if pending_be:
            be_armed = True
            pending_be = False

        # Active stop: initial until BE arms on the bar *after* TP1.
        active_stop = entry_px if be_armed else stop_px

        # 1) Stop against remaining units (conservative before targets).
        stop_hit = (side == "long" and l <= active_stop) or (side == "short" and h >= active_stop)
        if stop_hit and remaining:
            reason = "be_stop" if be_armed else "stop"
            for unit in sorted(remaining):
                exits.append(
                    UnitExit(unit, stamp.isoformat(), active_stop, reason, _unit_pl(side, entry_px, active_stop))
                )
            remaining.clear()
            return _finalize(
                session=session,
                side=side,
                london_high=london_high,
                london_low=london_low,
                risk=risk,
                sweep_ts=sweep_ts,
                entry_ts=entry_ts,
                entry_px=entry_px,
                initial_stop=initial_stop,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                exits=exits,
            )

        # 2) Scale targets on remaining units (1R → 2R → 3R).
        hit_tp1_this_bar = False
        if side == "long":
            if 1 in remaining and h >= tp1:
                exits.append(UnitExit(1, stamp.isoformat(), tp1, "tp1", _unit_pl(side, entry_px, tp1)))
                remaining.discard(1)
                hit_tp1_this_bar = True
            if 2 in remaining and h >= tp2:
                exits.append(UnitExit(2, stamp.isoformat(), tp2, "tp2", _unit_pl(side, entry_px, tp2)))
                remaining.discard(2)
            if 3 in remaining and h >= tp3:
                exits.append(UnitExit(3, stamp.isoformat(), tp3, "tp3", _unit_pl(side, entry_px, tp3)))
                remaining.discard(3)
        else:
            if 1 in remaining and l <= tp1:
                exits.append(UnitExit(1, stamp.isoformat(), tp1, "tp1", _unit_pl(side, entry_px, tp1)))
                remaining.discard(1)
                hit_tp1_this_bar = True
            if 2 in remaining and l <= tp2:
                exits.append(UnitExit(2, stamp.isoformat(), tp2, "tp2", _unit_pl(side, entry_px, tp2)))
                remaining.discard(2)
            if 3 in remaining and l <= tp3:
                exits.append(UnitExit(3, stamp.isoformat(), tp3, "tp3", _unit_pl(side, entry_px, tp3)))
                remaining.discard(3)

        if hit_tp1_this_bar:
            pending_be = True

        if not remaining:
            return _finalize(
                session=session,
                side=side,
                london_high=london_high,
                london_low=london_low,
                risk=risk,
                sweep_ts=sweep_ts,
                entry_ts=entry_ts,
                entry_px=entry_px,
                initial_stop=initial_stop,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                exits=exits,
            )

    if entry_ts is None or sweep_ts is None or not remaining:
        if exits:
            return _finalize(
                session=session,
                side=side,
                london_high=london_high,
                london_low=london_low,
                risk=risk,
                sweep_ts=sweep_ts,  # type: ignore[arg-type]
                entry_ts=entry_ts,  # type: ignore[arg-type]
                entry_px=entry_px,
                initial_stop=initial_stop,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                exits=exits,
            )
        return None

    last = window.iloc[-1]
    last_ts = pd.Timestamp(window.index[-1])
    exit_px = float(last["close"])
    for unit in sorted(remaining):
        exits.append(UnitExit(unit, last_ts.isoformat(), exit_px, "eod", _unit_pl(side, entry_px, exit_px)))
    return _finalize(
        session=session,
        side=side,
        london_high=london_high,
        london_low=london_low,
        risk=risk,
        sweep_ts=sweep_ts,
        entry_ts=entry_ts,
        entry_px=entry_px,
        initial_stop=initial_stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        exits=exits,
    )


def run_backtest(bars_by_day: Dict[date, pd.DataFrame], start: date, end: Optional[date] = None) -> List[LondonSweepTrade]:
    sessions = sorted(d for d in bars_by_day if d >= start and (end is None or d <= end))
    trades: List[LondonSweepTrade] = []
    for session in sessions:
        frame = _session_frame(bars_by_day, session)
        if frame.empty:
            continue
        trade = _simulate_day(frame, session)
        if trade is not None:
            trades.append(trade)
    return trades


def _draw_trade(ax, trade: LondonSweepTrade) -> None:
    color = "#006dce" if trade.side == "long" else "#7b3fb2"
    marker = "^" if trade.side == "long" else "v"
    entry_ts = pd.Timestamp(trade.entry_ts)
    sweep_ts = pd.Timestamp(trade.sweep_ts) if trade.sweep_ts else None
    ax.scatter([entry_ts], [trade.entry_price], s=120, color=color, marker=marker, zorder=10)
    ax.axvline(entry_ts, color=color, linewidth=1.4, alpha=0.85)
    if sweep_ts is not None:
        ax.axvline(sweep_ts, color="#ef6c00", linewidth=1.1, alpha=0.75, linestyle=":")
        ax.text(
            sweep_ts,
            trade.london_high if trade.side == "short" else trade.london_low,
            " sweep",
            color="#ef6c00",
            fontsize=8,
            va="bottom",
        )

    exits = trade.exits or [UnitExit(**row) for row in json.loads(trade.exits_json or "[]")]
    for ex in exits:
        exit_ts = pd.Timestamp(ex.ts)
        if ex.reason.startswith("tp"):
            m = "o"
        elif ex.reason in {"stop", "be_stop"}:
            m = "x"
        else:
            m = "s"
        ax.scatter([exit_ts], [ex.price], s=55, color=color, marker=m, zorder=10)
        ax.text(exit_ts, ex.price, " u%d" % ex.unit, color=color, fontsize=7, va="bottom")

    last_ts = pd.Timestamp(trade.exit_ts)
    ax.hlines(trade.initial_stop, entry_ts, last_ts, colors="#c62828", linestyles=":", linewidth=0.9, alpha=0.55)
    ax.hlines(trade.entry_price, entry_ts, last_ts, colors="#455a64", linestyles="--", linewidth=0.9, alpha=0.55)
    ax.hlines(trade.tp1, entry_ts, last_ts, colors="#2e7d32", linestyles="-", linewidth=0.9, alpha=0.7)
    ax.hlines(trade.tp2, entry_ts, last_ts, colors="#2e7d32", linestyles="--", linewidth=0.9, alpha=0.7)
    ax.hlines(trade.tp3, entry_ts, last_ts, colors="#2e7d32", linestyles=":", linewidth=1.0, alpha=0.7)
    ax.text(
        entry_ts,
        trade.entry_price,
        " %s $%.0f" % (trade.side, trade.net_usd),
        color=color,
        fontsize=8,
        va="bottom",
        zorder=11,
    )


def build_charts(
    trades: List[LondonSweepTrade],
    bars_by_day: Dict[date, pd.DataFrame],
    output_root: Path,
    max_charts: int,
) -> None:
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    adapters = [
        FillTrade(
            trade_id=t.session,
            side=t.side,
            entry_ts=pd.Timestamp(t.entry_ts),
            entry_price=t.entry_price,
            exit_ts=pd.Timestamp(t.exit_ts),
            exit_price=t.exit_price,
            net_usd=t.net_usd,
        )
        for t in trades
    ]
    selected_ids = {a.trade_id for a in _select_trades(adapters, max_charts)}
    selected = sorted([t for t in trades if t.session in selected_ids], key=lambda t: t.entry_ts)[:max_charts]

    rows = []
    for idx, trade in enumerate(selected, start=1):
        session = date.fromisoformat(trade.session)
        frame = _session_frame(bars_by_day, session)
        start_ts = _ts(session, KZ_START)
        end_ts = _ts(session, NY_CLOSE)
        win = frame[(frame.index >= start_ts) & (frame.index < end_ts)].copy()
        if win.empty:
            continue
        if "volume" not in win.columns:
            win["volume"] = 0.0
        candles = _resample_5m(win)
        if candles.empty:
            continue

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(17, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)
        kz0, kz1 = _ts(session, KZ_START), _ts(session, KZ_END)
        ax.axvspan(kz0, kz1, color="#ffcc80", alpha=0.12, zorder=0, label="London KZ 02-05 NY")
        ax.hlines(
            trade.london_high,
            start_ts,
            end_ts,
            colors="#ef6c00",
            linestyles="--",
            linewidth=1.35,
            alpha=0.95,
            label="London high/low",
        )
        ax.hlines(trade.london_low, start_ts, end_ts, colors="#ef6c00", linestyles="--", linewidth=1.35, alpha=0.95)
        ax.text(kz0, trade.london_high, " London high", color="#ef6c00", fontsize=8, va="bottom")
        ax.text(kz0, trade.london_low, " London low", color="#ef6c00", fontsize=8, va="top")
        _draw_trade(ax, trade)
        ax.set_title(
            "EURUSD London sweep 1/1/1 — %s — %s — net $%.0f (%s)"
            % (trade.session, trade.side, trade.net_usd, trade.exit_reason)
        )
        ax.set_ylabel(INSTRUMENT)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)
        ax.set_xlim(start_ts, end_ts)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(5 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        vol_ax.set_xlim(start_ts, end_ts)
        fig.autofmt_xdate()

        rel = Path("charts") / (
            "%03d_%s_%s_%s.png" % (idx, trade.session, trade.side, "win" if trade.net_usd > 0 else "loss")
        )
        fig.savefig(output_root / rel, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": trade.session,
                "side": trade.side,
                "net": trade.net_usd,
                "exit_reason": trade.exit_reason,
                "r_mult": trade.r_mult,
                "chart": str(rel),
            }
        )
        if idx % 25 == 0:
            print("  charted %d/%d" % (idx, len(selected)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# EURUSD London sweep 1/1/1 charts",
        "",
        "Even sample of **%d** trades. Scaleout **1R / 2R / 3R**, stop → BE after TP1." % len(rows),
        "",
        "| # | Session | Side | Net | Exit | Campaign R | Chart |",
        "|---:|---|---|---:|---|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${net:,.2f} | {exit_reason} | {r_mult:.2f} | [{chart}]({chart}) |".format(**item)
        )
    (output_root / "CHARTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize(trades: List[LondonSweepTrade]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "units": 0,
            "net_usd": 0.0,
            "wins": 0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "max_dd": 0.0,
            "longs": 0,
            "shorts": 0,
            "tp1": 0,
            "tp2": 0,
            "tp3": 0,
            "stops": 0,
            "be_stops": 0,
            "eod": 0,
        }
    nets = [t.net_usd for t in trades]
    equity = np.cumsum(nets)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    wins = sum(1 for n in nets if n > 0)
    tp1 = tp2 = tp3 = stops = be_stops = eod = 0
    for t in trades:
        for ex in t.exits or [UnitExit(**row) for row in json.loads(t.exits_json or "[]")]:
            if ex.reason == "tp1":
                tp1 += 1
            elif ex.reason == "tp2":
                tp2 += 1
            elif ex.reason == "tp3":
                tp3 += 1
            elif ex.reason == "stop":
                stops += 1
            elif ex.reason == "be_stop":
                be_stops += 1
            elif ex.reason == "eod":
                eod += 1
    return {
        "trades": len(trades),
        "units": len(trades) * UNITS,
        "net_usd": float(sum(nets)),
        "wins": wins,
        "win_rate": 100.0 * wins / len(trades),
        "avg_r": float(np.mean([t.r_mult for t in trades])),
        "max_dd": float(dd.min()) if len(dd) else 0.0,
        "longs": sum(1 for t in trades if t.side == "long"),
        "shorts": sum(1 for t in trades if t.side == "short"),
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "stops": stops,
        "be_stops": be_stops,
        "eod": eod,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_london_sweep_reversal_scaleout111",
    )
    parser.add_argument("--start", default="2015-01-02")
    parser.add_argument("--max-charts", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if args.force and args.output_root.exists():
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)

    one_m, _daily = ensure_eurusd_platform_files(REPO, force=False)
    print("Loading EURUSD 1m...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    start = date.fromisoformat(args.start)
    print("Simulating London sweep 1/1/1 from %s..." % start.isoformat(), flush=True)
    trades = run_backtest(bars_by_day, start)
    stats = summarize(trades)
    print(
        "trades=%d net=$%.2f win=%.1f%% avgR=%.2f maxDD=$%.2f "
        "(L/S=%d/%d tp1/2/3=%d/%d/%d stop/be/eod=%d/%d/%d)"
        % (
            stats["trades"],
            stats["net_usd"],
            stats["win_rate"],
            stats["avg_r"],
            stats["max_dd"],
            stats["longs"],
            stats["shorts"],
            stats["tp1"],
            stats["tp2"],
            stats["tp3"],
            stats["stops"],
            stats["be_stops"],
            stats["eod"],
        ),
        flush=True,
    )

    trades_csv = args.output_root / "trades.csv"
    fieldnames = [
        "session",
        "side",
        "london_high",
        "london_low",
        "sweep_ts",
        "entry_ts",
        "entry_price",
        "initial_stop",
        "tp1",
        "tp2",
        "tp3",
        "exit_ts",
        "exit_price",
        "exit_reason",
        "net_usd",
        "r_mult",
        "exits_json",
    ]
    with trades_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            row = {k: getattr(t, k) for k in fieldnames}
            writer.writerow(row)

    pd.DataFrame([stats]).to_csv(args.output_root / "summary.csv", index=False)
    lines = [
        "# EURUSD London sweep reversal — scaleout 1/1/1",
        "",
        "- London H/L: **02:00–05:00 NY**",
        "- After KZ: first sweep sets bias (low→long / high→short)",
        "- Entry at opposite London level; initial SL at swept level",
        "- **3 units**: TP **1R / 2R / 3R**; after TP1, SL → **breakeven** (next bar)",
        "- EOD flatten **16:00 NY**; fee $%.2f / unit" % FEE_PER_UNIT,
        "",
        "| Trades | Units | Long/Short | Net | Win% | Avg campaign R | Max DD | TP1/2/3 | Stop/BE/EOD |",
        "|---:|---:|---:|---:|---:|---:|---:|---|---|",
        "| %d | %d | %d/%d | $%.2f | %.1f | %.2f | $%.2f | %d/%d/%d | %d/%d/%d |"
        % (
            stats["trades"],
            stats["units"],
            stats["longs"],
            stats["shorts"],
            stats["net_usd"],
            stats["win_rate"],
            stats["avg_r"],
            stats["max_dd"],
            stats["tp1"],
            stats["tp2"],
            stats["tp3"],
            stats["stops"],
            stats["be_stops"],
            stats["eod"],
        ),
        "",
        "- Trades: `%s`" % trades_csv.as_posix(),
        "",
    ]
    (args.output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

    print("Building %d charts..." % args.max_charts, flush=True)
    build_charts(trades, bars_by_day, args.output_root, args.max_charts)
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    print("Wrote %s" % (args.output_root / "CHARTS.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
