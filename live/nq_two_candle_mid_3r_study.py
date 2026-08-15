"""NQ RTH 15m — first-two-candle bias, mid retest, 3R, morning-only (before noon).

Rules (v1.1 — see live/state/nq_two_candle_mid_3r/SPEC.md):
- After NY open, wait for the first two 15m candles (09:30, 09:45).
- Candle-2 color sets bias (green→long, red→short; doji→no trade day).
- Entry at defining candle midpoint; SL at far extreme; target 3R.
- Max 2 trades/day; **entries only before 12:00 NY**; flatten open risk at noon.
- Bias flip: long if close < defining low; short if close > defining high.
- After stop, same bias → next same-color candle (not the stop bar) redefines entry.
- After bias flip → next opposite-color candle defines new-side entry.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from .bars import rth_bars
from .replay_audit import POINT_VALUES
from .trend_momentum_common import resample_n_min
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "nq_two_candle_mid_3r"
NY = "America/New_York"
POINT_VALUE = float(POINT_VALUES["NQ"])
FEE = 1.50
TICK = 0.25
MAX_TRADES = 2
R_MULT = 3.0
# No new entries at/after this NY clock time; open positions flatten here.
MORNING_END = time(12, 0)


@dataclass
class DefCandle:
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float

    @property
    def mid(self) -> float:
        return 0.5 * (self.high + self.low)

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open


@dataclass
class Trade:
    session: date
    trade_num: int
    side: str
    bias_at_entry: str
    def_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    r_pts: float
    pnl_pts: float
    net_usd: float


def _color(row: pd.Series) -> Optional[str]:
    o, c = float(row["open"]), float(row["close"])
    if c > o:
        return "green"
    if c < o:
        return "red"
    return None


def _as_def(ts: pd.Timestamp, row: pd.Series) -> DefCandle:
    return DefCandle(
        ts=pd.Timestamp(ts),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
    )


def _levels(side: str, mid: float, high: float, low: float) -> Tuple[float, float, float]:
    if side == "long":
        entry = mid
        stop = low
        r = entry - stop
        if r <= 0:
            return entry, stop, entry
        target = entry + R_MULT * r
        return entry, stop, target
    entry = mid
    stop = high
    r = stop - entry
    if r <= 0:
        return entry, stop, entry
    target = entry - R_MULT * r
    return entry, stop, target


def _touch_entry(side: str, entry: float, row: pd.Series) -> bool:
    if side == "long":
        return float(row["low"]) <= entry
    return float(row["high"]) >= entry


def _manage_exit(
    side: str,
    entry: float,
    stop: float,
    target: float,
    row: pd.Series,
    *,
    slippage_ticks: float,
) -> Optional[Tuple[float, str]]:
    """Conservative: if both stop and target touched in same bar, take stop."""
    slip = slippage_ticks * TICK
    lo, hi, op = float(row["low"]), float(row["high"]), float(row["open"])
    if side == "long":
        stop_hit = lo <= stop
        tgt_hit = hi >= target
        if stop_hit and tgt_hit:
            return min(op, stop - slip), "stop"
        if stop_hit:
            return min(op, stop - slip), "stop"
        if tgt_hit:
            return max(op, target), "target"  # no positive slip on target
        return None
    stop_hit = hi >= stop
    tgt_hit = lo <= target
    if stop_hit and tgt_hit:
        return max(op, stop + slip), "stop"
    if stop_hit:
        return max(op, stop + slip), "stop"
    if tgt_hit:
        return min(op, target), "target"
    return None


def simulate_day(
    session: date,
    m15: pd.DataFrame,
    *,
    slippage_ticks: float = 1.0,
    max_trades: int = MAX_TRADES,
) -> List[Trade]:
    if len(m15) < 3:
        return []

    bars = list(m15.iterrows())
    # First two RTH 15m candles
    ts0, r0 = bars[0]
    ts1, r1 = bars[1]
    # Sanity: expect 09:30 and 09:45
    t0 = pd.Timestamp(ts0).tz_convert(NY).time()
    t1 = pd.Timestamp(ts1).tz_convert(NY).time()
    if t0 != time(9, 30) or t1 != time(9, 45):
        # Still allow if session starts late / early close quirks — require ≥2 bars
        pass

    c2_color = _color(r1)
    if c2_color is None:
        return []

    bias = "long" if c2_color == "green" else "short"
    defining = _as_def(ts1, r1)
    excluded_ts: Optional[pd.Timestamp] = None
    trades: List[Trade] = []

    in_pos = False
    side = bias
    entry = stop = target = 0.0
    entry_ts: Optional[pd.Timestamp] = None
    def_ts = defining.ts
    r_pts = 0.0
    pending = False

    def arm_from(defn: DefCandle, side_: str) -> None:
        nonlocal pending, defining, side, entry, stop, target, def_ts, r_pts
        defining = defn
        side = side_
        entry, stop, target = _levels(side_, defn.mid, defn.high, defn.low)
        def_ts = defn.ts
        r_pts = abs(entry - stop)
        pending = r_pts > 0

    # Arm from candle 2; fills allowed only on later bars (index >= 2).
    arm_from(defining, bias)

    # Walk bars starting at index 2 (first bar after candle-2 completes)
    for i in range(2, len(bars)):
        ts, row = bars[i]
        ts = pd.Timestamp(ts)
        bar_t = ts.tz_convert(NY).time() if ts.tzinfo else ts.time()
        morning = bar_t < MORNING_END
        color = _color(row)

        # --- manage open trade ---
        if in_pos:
            hit = _manage_exit(side, entry, stop, target, row, slippage_ticks=slippage_ticks)
            # Flatten at noon (first bar at/after 12:00) or last RTH bar
            if hit is None and (not morning or i == len(bars) - 1):
                hit = (float(row["close"]), "noon" if not morning else "eod")
            if hit is not None:
                exit_px, reason = hit
                pnl_pts = (exit_px - entry) if side == "long" else (entry - exit_px)
                trades.append(
                    Trade(
                        session=session,
                        trade_num=len(trades) + 1,
                        side=side,
                        bias_at_entry=bias,
                        def_ts=def_ts,
                        entry_ts=entry_ts or ts,
                        entry=entry,
                        stop=stop,
                        target=target,
                        exit_ts=ts,
                        exit=exit_px,
                        exit_reason=reason,
                        r_pts=r_pts,
                        pnl_pts=pnl_pts,
                        net_usd=pnl_pts * POINT_VALUE - FEE,
                    )
                )
                in_pos = False
                pending = False
                if reason == "stop":
                    excluded_ts = ts
                else:
                    excluded_ts = None
                # After exit, check bias flip on this same bar's close before re-arming
                if bias == "long" and float(row["close"]) < defining.low:
                    bias = "short"
                    pending = False
                    defining = DefCandle(ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
                    # need next red to arm
                elif bias == "short" and float(row["close"]) > defining.high:
                    bias = "long"
                    pending = False
                    defining = DefCandle(ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
                # Re-arm only in the morning window
                if morning and len(trades) < max_trades:
                    if bias == "long" and color == "green" and ts != excluded_ts:
                        arm_from(_as_def(ts, row), "long")
                    elif bias == "short" and color == "red" and ts != excluded_ts:
                        arm_from(_as_def(ts, row), "short")
                else:
                    pending = False
                if not morning:
                    break
                continue

            # Still in trade: optional bias update for next time (don't flatten)
            if bias == "long" and float(row["close"]) < defining.low:
                bias = "short"
            elif bias == "short" and float(row["close"]) > defining.high:
                bias = "long"
            continue

        # --- flat: morning-only entries ---
        if not morning:
            pending = False
            break
        if len(trades) >= max_trades:
            break

        # Bias flip vs current defining extreme (while flat / waiting)
        flipped = False
        if bias == "long" and float(row["close"]) < defining.low:
            bias = "short"
            pending = False
            flipped = True
            excluded_ts = None
        elif bias == "short" and float(row["close"]) > defining.high:
            bias = "long"
            pending = False
            flipped = True
            excluded_ts = None

        # New defining candle of active bias color
        if bias == "long" and color == "green" and ts != excluded_ts:
            arm_from(_as_def(ts, row), "long")
            # entry only on *subsequent* bars — skip fill this bar
            continue
        if bias == "short" and color == "red" and ts != excluded_ts:
            arm_from(_as_def(ts, row), "short")
            continue

        if flipped:
            continue

        # Try fill pending limit at mid
        if pending and r_pts > 0 and _touch_entry(side, entry, row):
            # Enter, then check exit on same bar (stop first)
            entry_ts = ts
            in_pos = True
            pending = False
            hit = _manage_exit(side, entry, stop, target, row, slippage_ticks=slippage_ticks)
            if hit is not None:
                exit_px, reason = hit
                pnl_pts = (exit_px - entry) if side == "long" else (entry - exit_px)
                trades.append(
                    Trade(
                        session=session,
                        trade_num=len(trades) + 1,
                        side=side,
                        bias_at_entry=bias,
                        def_ts=def_ts,
                        entry_ts=entry_ts,
                        entry=entry,
                        stop=stop,
                        target=target,
                        exit_ts=ts,
                        exit=exit_px,
                        exit_reason=reason,
                        r_pts=r_pts,
                        pnl_pts=pnl_pts,
                        net_usd=pnl_pts * POINT_VALUE - FEE,
                    )
                )
                in_pos = False
                if reason == "stop":
                    excluded_ts = ts
                else:
                    excluded_ts = None
                if len(trades) < max_trades:
                    if bias == "long" and color == "green" and ts != excluded_ts:
                        arm_from(_as_def(ts, row), "long")
                    elif bias == "short" and color == "red" and ts != excluded_ts:
                        arm_from(_as_def(ts, row), "short")

    return trades


def summarize(trades: Sequence[Trade]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "net_usd": 0.0,
            "stress_dd_usd": 0.0,
            "ns": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_trade": 0.0,
            "targets": 0,
            "stops": 0,
            "eod": 0,
            "noon": 0,
            "longs": 0,
            "shorts": 0,
            "sessions": 0,
        }
    net = sum(t.net_usd for t in trades)
    wins = [t for t in trades if t.net_usd > 0]
    losses = [t for t in trades if t.net_usd <= 0]
    gw = sum(t.net_usd for t in wins)
    gl = abs(sum(t.net_usd for t in losses))
    equity = peak = 0.0
    dd = 0.0
    for t in trades:
        equity += t.net_usd
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    sessions = len({t.session for t in trades})
    return {
        "trades": len(trades),
        "net_usd": net,
        "stress_dd_usd": dd,
        "ns": (net / abs(dd)) if dd < 0 else (math.inf if net > 0 else 0.0),
        "win_rate_pct": 100.0 * len(wins) / len(trades),
        "profit_factor": (gw / gl) if gl > 0 else math.inf,
        "avg_trade": net / len(trades),
        "targets": sum(1 for t in trades if t.exit_reason == "target"),
        "stops": sum(1 for t in trades if t.exit_reason == "stop"),
        "eod": sum(1 for t in trades if t.exit_reason == "eod"),
        "noon": sum(1 for t in trades if t.exit_reason == "noon"),
        "longs": sum(1 for t in trades if t.side == "long"),
        "shorts": sum(1 for t in trades if t.side == "short"),
        "sessions": sessions,
    }


def write_outputs(out: Path, trades: List[Trade], summary: dict, *, note: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in trades])
    if not df.empty:
        df["session"] = df["session"].astype(str)
        df["def_ts"] = df["def_ts"].astype(str)
        df["entry_ts"] = df["entry_ts"].astype(str)
        df["exit_ts"] = df["exit_ts"].astype(str)
    df.to_csv(out / "trades.csv", index=False)
    pd.DataFrame([summary]).to_csv(out / "summary.csv", index=False)

    ns = summary["ns"]
    ns_s = "inf" if ns == math.inf else "%.2f" % ns
    lines = [
        "# NQ two-candle mid 3R",
        "",
        note,
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Trades | %d |" % summary["trades"],
        "| Sessions w/ trades | %d |" % summary["sessions"],
        "| Net USD | %+.0f |" % summary["net_usd"],
        "| Stress DD USD | %+.0f |" % summary["stress_dd_usd"],
        "| N/S | %s |" % ns_s,
        "| Win rate | %.1f%% |" % summary["win_rate_pct"],
        "| Profit factor | %.2f |" % (summary["profit_factor"] if summary["profit_factor"] != math.inf else float("nan")),
        "| Avg trade | %+.1f |" % summary["avg_trade"],
        "| Targets / Stops / Noon / EOD | %d / %d / %d / %d |"
        % (summary["targets"], summary["stops"], summary.get("noon", 0), summary["eod"]),
        "| Long / Short | %d / %d |" % (summary["longs"], summary["shorts"]),
        "",
        "Artifacts: [`trades.csv`](trades.csv), [`summary.csv`](summary.csv), [`SPEC.md`](SPEC.md).",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_spec(out: Path) -> None:
    text = """# NQ two-candle midpoint 3R — SPEC (v1.1 morning)

## Setup
- Instrument: **NQ** front-month, **RTH morning only** (entries **09:30–11:59** America/New_York; flatten open risk at **12:00**)
- Signal / management TF: **15m** (`resample` left/left on RTH 1m)
- Economics: $20/pt, $1.50/contract/trade, 1-tick stop slippage; conservative same-bar stop-before-target

## Bias
1. Wait for the first two RTH 15m candles (09:30 & 09:45).
2. If candle 2 is **green** (close > open) → **long** bias; if **red** → **short**; doji → no trades that day.
3. Candle 2 is the initial **entry-defining** candle.

## Entry / risk
- Enter **limit** at defining candle **midpoint** `(H+L)/2` on a **later** morning bar that trades through it.
- Long: SL = defining **low**; Short: SL = defining **high**.
- Target = **3R** (`entry ± 3 × |entry − SL|`).
- Max **1** open position; max **2** trades per morning; **no new entries at/after 12:00**; flatten at noon if still open.

## Redefine / re-entry
- While **flat** and bias unchanged (morning only), each new same-color candle becomes the new defining candle.
- After a **stop**, the stop bar is **excluded**; wait for the next same-color candle (if bias unchanged).
- **Bias flip (long→short):** a 15m **close below** the current defining candle’s **low**.
- **Bias flip (short→long):** a 15m **close above** the current defining candle’s **high**.
- After a flip, wait for the first candle of the **new** bias color, then arm mid entry.

## Notes / assumptions
- “Closes over the low” on the long side is implemented as **close below the low** (symmetric to short-side close above high).
- Filling uses 15m OHLC touch (not 1m pathing).
- No pyramiding; wins (target/noon) also require a fresh defining candle to re-enter.
"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "SPEC.md").write_text(text, encoding="utf-8")


def run(*, start: Optional[date] = None, end: Optional[date] = None, out: Path = OUT) -> dict:
    write_spec(out)
    cfg = MARKETS["nq"]
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), "nq")
    all_trades: List[Trade] = []
    days = 0
    session_m15: dict = {}
    for session, day_1m in sorted(by_day.items()):
        if start and session < start:
            continue
        if end and session > end:
            continue
        rth = rth_bars(day_1m, session, dense=False)
        if rth is None or rth.empty:
            continue
        m15 = resample_n_min(rth, 15)
        if m15.empty:
            continue
        days += 1
        session_m15[session] = m15
        all_trades.extend(simulate_day(session, m15))

    summary = summarize(all_trades)
    summary["rth_sessions_scanned"] = days
    note = (
        "NQ RTH **morning-only** (entries before 12:00 NY; flatten at noon) "
        "15m first-two-candle bias → mid retest → 3R; max 2 trades/day. "
        "Scanned **%d** RTH sessions." % days
    )
    if start or end:
        note += " Window: %s → %s." % (start or "start", end or "end")
    write_outputs(out, all_trades, summary, note=note)
    # stash for charting without reloading DBN
    run._last_session_m15 = session_m15  # type: ignore[attr-defined]
    run._last_trades = all_trades  # type: ignore[attr-defined]
    return summary


def _plot_trade_chart(m15: pd.DataFrame, trade: Trade, out_path: Path, idx: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np

    # Morning window + a little context
    start = pd.Timestamp.combine(trade.session, time(9, 30)).tz_localize(NY)
    end = pd.Timestamp.combine(trade.session, time(12, 30)).tz_localize(NY)
    plot = m15[(m15.index >= start) & (m15.index <= end)].copy()
    if plot.empty:
        plot = m15.copy()

    x = mdates.date2num(plot.index.to_pydatetime())
    width = (15.0 / (24.0 * 60.0)) * 0.72
    result = "win" if trade.net_usd > 0 else "loss"
    result_color = "#168a5a" if result == "win" else "#c43d3d"
    entry_x = mdates.date2num(pd.Timestamp(trade.entry_ts).to_pydatetime())
    exit_x = mdates.date2num(pd.Timestamp(trade.exit_ts).to_pydatetime())
    def_x = mdates.date2num(pd.Timestamp(trade.def_ts).to_pydatetime())

    fig, ax = plt.subplots(figsize=(16, 7))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.9, zorder=3)
    span = float(plot["high"].max() - plot["low"].min())
    min_body = max(span * 0.001, 1e-6)
    for xi, o, c, col in zip(x, plot["open"], plot["close"], colors):
        bottom = min(o, c)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                max(abs(c - o), min_body),
                facecolor=col,
                edgecolor=col,
                linewidth=0.4,
                alpha=0.85,
                zorder=4,
            )
        )

    ax.axvline(def_x, color="#1565c0", linestyle=":", linewidth=1.2, alpha=0.9, label="Defining candle")
    ax.axhline(trade.entry, color="#333333", linestyle="--", linewidth=1.1, label="Entry mid %.2f" % trade.entry)
    ax.axhline(trade.stop, color="#ef6c00", linestyle=":", linewidth=1.2, label="Stop %.2f" % trade.stop)
    ax.axhline(trade.target, color="#6a1b9a", linestyle=":", linewidth=1.2, label="Target 3R %.2f" % trade.target)
    ax.axvspan(entry_x, exit_x, color=result_color, alpha=0.10, zorder=0)
    ax.axvline(entry_x, color=result_color, linewidth=1.2)
    ax.axvline(exit_x, color=result_color, linewidth=1.2, linestyle="--")
    # Noon line
    noon = pd.Timestamp.combine(trade.session, time(12, 0)).tz_localize(NY)
    ax.axvline(mdates.date2num(noon.to_pydatetime()), color="#888888", linestyle="-.", linewidth=1.0, alpha=0.7, label="Noon cutoff")

    marker = "^" if trade.side == "long" else "v"
    ax.scatter([entry_x], [trade.entry], marker=marker, s=120, color=result_color, edgecolors="white", zorder=8)
    ax.scatter([exit_x], [trade.exit], marker="X", s=100, color=result_color, edgecolors="white", zorder=8)

    ax.set_title(
        "NQ morning mid-3R — #%02d %s %s | $%+.0f | %s → %s (%s)"
        % (
            idx,
            result.upper(),
            trade.side,
            trade.net_usd,
            pd.Timestamp(trade.entry_ts).strftime("%Y-%m-%d %H:%M"),
            pd.Timestamp(trade.exit_ts).strftime("%H:%M"),
            trade.exit_reason,
        ),
        fontsize=10,
    )
    ax.set_ylabel("NQ")
    ax.grid(True, color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=plot.index.tz))
    ax.set_xlabel("Time (America/New_York)")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def write_charts(
    out: Path,
    trades: List[Trade],
    session_m15: dict,
    *,
    n: int = 50,
    seed: int = 42,
) -> int:
    import random
    import shutil

    charts_root = out / "charts"
    if charts_root.exists():
        shutil.rmtree(charts_root)
    charts_root.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    wins = [t for t in trades if t.net_usd > 0]
    losses = [t for t in trades if t.net_usd <= 0]
    n_w = min(n // 2, len(wins))
    n_l = min(n - n_w, len(losses))
    # if not enough wins, fill with more losses
    if n_w + n_l < n:
        n_l = min(n - n_w, len(losses))
    picked = rng.sample(wins, n_w) + rng.sample(losses, n_l)
    # wins first then losses for stable numbering
    ordered = [t for t in picked if t.net_usd > 0] + [t for t in picked if t.net_usd <= 0]

    lines = [
        "# NQ morning mid-3R — sample charts",
        "",
        "Morning-only (before noon). Sample of **%d** trades (%d wins + %d losses), seed `%d`."
        % (len(ordered), n_w, n_l, seed),
        "",
        "| # | Result | Side | Entry | Exit | $ | Reason | Chart |",
        "|---:|---|---|---|---|---:|---|---|",
    ]
    written = 0
    for i, trade in enumerate(ordered, start=1):
        m15 = session_m15.get(trade.session)
        if m15 is None:
            continue
        result = "win" if trade.net_usd > 0 else "loss"
        stamp = pd.Timestamp(trade.entry_ts).strftime("%Y-%m-%d_%H%M")
        rel = "charts/%02d_%s_%s.png" % (i, result, stamp)
        _plot_trade_chart(m15, trade, out / rel, i)
        written += 1
        lines.append(
            "| %d | %s | %s | %s | %s | %+.0f | %s | [%s](%s) |"
            % (
                i,
                result,
                trade.side,
                pd.Timestamp(trade.entry_ts).strftime("%Y-%m-%d %H:%M"),
                pd.Timestamp(trade.exit_ts).strftime("%H:%M"),
                trade.net_usd,
                trade.exit_reason,
                rel,
                rel,
            )
        )
    (out / "CHARTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="", help="YYYY-MM-DD")
    ap.add_argument("--end", default="", help="YYYY-MM-DD")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--charts", type=int, default=50, help="Sample trade charts to write (0=skip)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    out = Path(args.out)
    summary = run(start=start, end=end, out=out)
    print("Wrote", out)
    for k, v in summary.items():
        print("  %s: %s" % (k, v))
    if args.charts > 0:
        session_m15 = getattr(run, "_last_session_m15", {})
        trades = getattr(run, "_last_trades", [])
        n = write_charts(out, trades, session_m15, n=args.charts, seed=args.seed)
        print("Wrote %d charts → %s/charts (see CHARTS.md)" % (n, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
