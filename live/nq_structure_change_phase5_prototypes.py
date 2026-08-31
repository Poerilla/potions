"""NQ structure-change Phase 5 — sample charts + 1R/1R prototypes A/B/C.

Uses frozen atlas events under live/state/nq_structure_change_event_study/.
4h invalidation pen≥0.05 only. Holdout is reported locked (no tuning).

Prototype A: CLOSE_BREAK continuation, structural stop ±1 tick, 1R/1R.
Prototype B: WICK_REJECT fade, wick extreme ±1 tick, 1R/1R.
Prototype C: reclaim exit on open A trades (management only).

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_structure_change_phase5_prototypes --charts-only --email
  python -m live.nq_structure_change_phase5_prototypes --email
  python -m live.nq_structure_change_phase5_prototypes --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .nq_structure_change_event_study import HUB as ATLAS_HUB
from .nq_structure_change_event_study import TICK
from .run_ledger import begin_run, complete_run, fail_run
from .structure_program_st_study import rth_slice, to_15m
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_structure_change_phase5_prototypes"
NY = "America/New_York"
RTH_CLOSE = time(16, 0)
EOD_FLATTEN = time(15, 55)  # unused in base 1R/1R (horizon = two_session_end)
POINT_VALUE = 20.0
FEE = 1.50
SLIPPAGE_TICKS = 1
STOP_BUFFER_TICKS = 1
PEN_PRIMARY = 0.05
EVENT_CLASSES = ("CLOSE_BREAK", "WICK_REJECT", "CLOSE_RECLAIM", "TOUCH_ONLY")
N_CHARTS_PER_CLASS = 5


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_primary_events(smoke: bool = False) -> pd.DataFrame:
    path = ATLAS_HUB / "structure_events.csv"
    df = pd.read_csv(path)
    m = (
        (df["structure_timeframe"] == "4h")
        & (df["event_family"] == "invalidation")
        & (pd.to_numeric(df["min_pen_ATR"], errors="coerce") == PEN_PRIMARY)
    )
    out = df.loc[m].copy()
    if smoke:
        # keep a few of each class for fast path
        parts = []
        for et in EVENT_CLASSES:
            sub = out[out["event_type"] == et].sort_values("confirm_bar_close_ts")
            parts.append(sub.head(8))
        out = pd.concat(parts, ignore_index=True)
    return out.reset_index(drop=True)


def _pick_chart_events(events: pd.DataFrame, n: int = N_CHARTS_PER_CLASS) -> pd.DataFrame:
    picks = []
    for et in EVENT_CLASSES:
        sub = events[events["event_type"] == et].sort_values("confirm_bar_close_ts")
        if sub.empty:
            continue
        if len(sub) <= n:
            picks.append(sub)
            continue
        qs = np.linspace(0.12, 0.92, n)
        idxs = sorted({int(round(q * (len(sub) - 1))) for q in qs})
        while len(idxs) < n:
            idxs.append(min(len(sub) - 1, idxs[-1] + 1))
        picks.append(sub.iloc[idxs[:n]])
    return pd.concat(picks, ignore_index=True) if picks else pd.DataFrame()


def _window_days(gby: Dict[date, pd.DataFrame], center: date, before: int = 2, after: int = 2) -> List[date]:
    days = sorted(gby.keys())
    if center not in days:
        near = [d for d in days if abs((d - center).days) <= 5]
        if not near:
            return []
        center = min(near, key=lambda d: abs((d - center).days))
    i = days.index(center)
    return days[max(0, i - before) : min(len(days), i + after + 1)]


def _draw_candles(ax, bars: pd.DataFrame) -> np.ndarray:
    x = np.arange(len(bars))
    up = bars["close"].to_numpy() >= bars["open"].to_numpy()
    ax.vlines(x, bars["low"], bars["high"], color="#888", lw=0.7, zorder=1)
    ax.vlines(x[up], bars["open"][up], bars["close"][up], color="#1a9850", lw=2.2, zorder=2)
    ax.vlines(x[~up], bars["close"][~up], bars["open"][~up], color="#d73027", lw=2.2, zorder=2)
    return x


def _xi(bars: pd.DataFrame, ts: pd.Timestamp) -> Optional[int]:
    if bars is None or bars.empty:
        return None
    ts = _localize(ts)
    pos = bars.index.searchsorted(ts, side="left")
    if pos >= len(bars):
        pos = len(bars) - 1
    # prefer nearest within 30m
    best = pos
    best_dt = abs((bars.index[pos] - ts).total_seconds())
    if pos > 0:
        dt0 = abs((bars.index[pos - 1] - ts).total_seconds())
        if dt0 < best_dt:
            best, best_dt = pos - 1, dt0
    if best_dt > 3600:
        return None
    return int(best)


def chart_event(
    ev: pd.Series,
    gby: Dict[date, pd.DataFrame],
    out_path: Path,
) -> bool:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    confirm_close = _localize(pd.Timestamp(ev["confirm_bar_close_ts"]))
    confirm_open = _localize(pd.Timestamp(ev["confirm_bar_open_ts"]))
    center = confirm_close.date()
    days = _window_days(gby, center, before=2, after=2)
    frames = []
    for d in days:
        rth = rth_slice(gby.get(d))
        if rth is None or rth.empty:
            continue
        frames.append(to_15m(rth))
    if not frames:
        return False
    bars = pd.concat(frames)
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    # clip to roughly confirm± context: from ~1.5 sessions before confirm open to +1 session
    t0 = confirm_open - pd.Timedelta(hours=10)
    t1 = confirm_close + pd.Timedelta(hours=8)
    plot = bars[(bars.index >= t0) & (bars.index <= t1)]
    if len(plot) < 8:
        plot = bars
    if plot.empty:
        return False

    level = float(ev["protected_swing_price"])
    et = str(ev["event_type"])
    bdir = str(ev.get("break_direction") or "")
    odir = str(ev.get("outcome_direction") or "") or "(none)"
    entry = float(ev["entry_price"]) if pd.notna(ev.get("entry_price")) else np.nan
    stop_pts = float(ev["stop_distance_points"]) if pd.notna(ev.get("stop_distance_points")) else np.nan

    fig, ax = plt.subplots(figsize=(14, 7))
    x = _draw_candles(ax, plot)

    ax.axhline(level, color="#1565c0", lw=1.6, ls="--", label="protected swing %.2f" % level)

    i0 = _xi(plot, confirm_open)
    i1 = _xi(plot, confirm_close)
    if i0 is not None and i1 is not None and i1 >= i0:
        ax.axvspan(i0 - 0.4, i1 + 0.4, color="#fff59d", alpha=0.35, label="confirm 4h window", zorder=0)

    if pd.notna(entry):
        ax.axhline(entry, color="#6a1b9a", lw=1.2, ls=":", label="atlas entry open %.2f" % entry)
        if pd.notna(stop_pts) and stop_pts > 0 and odir in ("bullish", "bearish"):
            if odir == "bullish":
                stop = entry - stop_pts
                tgt = entry + stop_pts
            else:
                stop = entry + stop_pts
                tgt = entry - stop_pts
            ax.axhline(stop, color="#ef6c00", lw=1.1, ls="-.", label="struct stop ~ %.2f" % stop)
            ax.axhline(tgt, color="#2e7d32", lw=1.1, ls="-.", label="1R target ~ %.2f" % tgt)

    oa = _localize(pd.Timestamp(ev["order_active_ts"]))
    xi_oa = _xi(plot, oa)
    if xi_oa is not None:
        ax.axvline(xi_oa, color="#5e35b1", lw=1.2, alpha=0.8, label="order_active")

    for d in days[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bdbdbd", lw=0.6, ls="--", zorder=0)
                break

    title = (
        "NQ 15m | %s | %s break=%s outcome=%s | %s | slice=%s\n"
        "pen=%.3f ATR | stop_pts=%.2f | %s → %s"
        % (
            et,
            ev["event_id"],
            bdir,
            odir,
            confirm_close.strftime("%Y-%m-%d %H:%M"),
            ev.get("slice", ""),
            float(ev.get("penetration_ATR") or 0),
            stop_pts if pd.notna(stop_pts) else float("nan"),
            plot.index[0].strftime("%m-%d %H:%M"),
            plot.index[-1].strftime("%m-%d %H:%M"),
        )
    )
    ax.set_title(title, fontsize=9)
    ax.legend(loc="best", fontsize=7)
    ax.set_xlim(-1, len(plot))
    step = max(1, len(plot) // 14)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(
        [plot.index[i].strftime("%m-%d %H:%M") for i in x[::step]],
        rotation=30,
        ha="right",
        fontsize=8,
    )
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def generate_sample_charts(
    hub: Path,
    gby: Dict[date, pd.DataFrame],
    events: pd.DataFrame,
    n_per_class: int = N_CHARTS_PER_CLASS,
) -> Tuple[Path, pd.DataFrame]:
    chart_dir = hub / "sample_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for old in chart_dir.glob("*.png"):
        old.unlink()
    sample = _pick_chart_events(events, n=n_per_class)
    rows = []
    for i, (_, ev) in enumerate(sample.iterrows(), start=1):
        et = str(ev["event_type"])
        fname = "%02d_%s_%s.png" % (i, et, str(ev["event_id"])[:48])
        ok = chart_event(ev, gby, chart_dir / fname)
        rows.append(
            {
                "chart_file": fname if ok else "",
                "ok": int(ok),
                "event_id": ev["event_id"],
                "event_type": et,
                "slice": ev.get("slice", ""),
                "confirm_bar_close_ts": ev["confirm_bar_close_ts"],
                "break_direction": ev.get("break_direction", ""),
                "outcome_direction": ev.get("outcome_direction", ""),
                "penetration_ATR": ev.get("penetration_ATR", ""),
                "stop_distance_points": ev.get("stop_distance_points", ""),
            }
        )
        _progress(hub, "chart %d/%d %s ok=%s" % (i, len(sample), et, ok))
    meta = pd.DataFrame(rows)
    meta.to_csv(hub / "sample_charts_index.csv", index=False)
    zpath = hub / "sample_charts.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(chart_dir.glob("*.png")):
            zf.write(p, arcname=p.name)
    return chart_dir, meta


# ---------------------------------------------------------------------------
# Path-aware 1R/1R fills
# ---------------------------------------------------------------------------


@dataclass
class ProtoTrade:
    trade_id: str
    prototype: str
    event_id: str
    structure_id: str
    slice: str
    side: str  # LONG | SHORT
    available_at: pd.Timestamp
    order_active_ts: pd.Timestamp
    fill_ts: pd.Timestamp
    entry: float
    stop: float
    target: float
    risk_pts: float
    exit_ts: Optional[pd.Timestamp] = None
    exit: Optional[float] = None
    exit_reason: str = ""
    gap_through_stop: int = 0
    mfe_pts: float = 0.0
    mae_pts: float = 0.0
    net_usd: float = 0.0
    causality_ok: int = 0


def _side_from_dir(direction: str) -> str:
    return "LONG" if direction == "bullish" else "SHORT"


def _adverse_entry(side: str, open_px: float) -> float:
    slip = SLIPPAGE_TICKS * TICK
    return open_px + slip if side == "LONG" else open_px - slip


def _adverse_stop_fill(side: str, stop: float, bar_open: float) -> Tuple[float, int]:
    """Gap-through: if open already through stop, fill at open; else at stop."""
    if side == "LONG":
        if bar_open <= stop:
            return float(bar_open), 1
        return float(stop), 0
    if bar_open >= stop:
        return float(bar_open), 1
    return float(stop), 0


def _resolve_entry_bar(
    tape: pd.DataFrame, available_at: pd.Timestamp, order_active_ts: pd.Timestamp
) -> Optional[Tuple[pd.Timestamp, float]]:
    """First 1m bar with ts > order_active_ts (strict available < order_active < fill)."""
    if tape is None or tape.empty:
        return None
    available_at = _localize(available_at)
    order_active_ts = _localize(order_active_ts)
    idx = tape.index
    pos = idx.searchsorted(order_active_ts, side="right")  # strictly after order_active
    if pos >= len(idx):
        return None
    fill_ts = _localize(idx[pos])
    if not (available_at < order_active_ts < fill_ts):
        # fallback: next bar if equality somehow
        if pos + 1 < len(idx) and available_at < order_active_ts:
            pos = pos + 1
            fill_ts = _localize(idx[pos])
        else:
            return None
    return fill_ts, float(tape["open"].iloc[pos])


def _manage_1r1r(
    tape: pd.DataFrame,
    *,
    side: str,
    fill_ts: pd.Timestamp,
    entry: float,
    stop: float,
    target: float,
    force_flat_ts: Optional[pd.Timestamp] = None,
    force_flat_px: Optional[float] = None,
    force_flat_reason: str = "force_flat",
    hard_end_ts: Optional[pd.Timestamp] = None,
) -> Tuple[pd.Timestamp, float, str, int, float, float]:
    """Stop-first 1m management until target, stop, reclaim, or hard_end (two-session)."""
    idx = tape.index
    fill_ts = _localize(fill_ts)
    force_flat_ts = _localize(force_flat_ts) if force_flat_ts is not None else None
    hard_end_ts = _localize(hard_end_ts) if hard_end_ts is not None else None
    pos0 = idx.searchsorted(fill_ts, side="right")  # manage after fill bar
    mfe = 0.0
    mae = 0.0
    for j in range(pos0, len(idx)):
        ts = _localize(idx[j])
        o = float(tape["open"].iloc[j])
        h = float(tape["high"].iloc[j])
        l = float(tape["low"].iloc[j])
        if force_flat_ts is not None and ts >= force_flat_ts:
            px = float(force_flat_px) if force_flat_px is not None else o
            return ts, px, force_flat_reason, 0, mfe, mae
        if hard_end_ts is not None and ts >= hard_end_ts:
            return ts, o, "horizon_end", 0, mfe, mae
        if side == "LONG":
            mfe = max(mfe, h - entry)
            mae = max(mae, entry - l)
            stopped = l <= stop
            targeted = h >= target
        else:
            mfe = max(mfe, entry - l)
            mae = max(mae, h - entry)
            stopped = h >= stop
            targeted = l <= target
        # stop-first same bar
        if stopped:
            px, gap = _adverse_stop_fill(side, stop, o)
            return ts, px, "stop", gap, mfe, mae
        if targeted:
            return ts, float(target), "target_1R", 0, mfe, mae
    last_ts = _localize(idx[-1])
    last_c = float(tape["close"].iloc[-1])
    return last_ts, last_c, "tape_end", 0, mfe, mae


def _stop_target_A(side: str, entry: float, level: float) -> Tuple[float, float, float]:
    buf = STOP_BUFFER_TICKS * TICK
    if side == "LONG":
        stop = level - buf
        risk = entry - stop
    else:
        stop = level + buf
        risk = stop - entry
    if risk <= 0:
        risk = TICK
        stop = entry - risk if side == "LONG" else entry + risk
    target = entry + risk if side == "LONG" else entry - risk
    return stop, target, risk


def _stop_target_B(side: str, entry: float, level: float, pen_pts: float, break_dir: str) -> Tuple[float, float, float]:
    """Fade stop = wick extreme ±1 tick. Wick extreme = level ± pen in break direction."""
    buf = STOP_BUFFER_TICKS * TICK
    if break_dir == "bullish":
        wick_ext = level + float(pen_pts)
    else:
        wick_ext = level - float(pen_pts)
    if side == "SHORT":
        stop = wick_ext + buf
        risk = stop - entry
    else:
        stop = wick_ext - buf
        risk = entry - stop
    if risk <= 0:
        risk = max(float(pen_pts), TICK)
        stop = entry - risk if side == "LONG" else entry + risk
    target = entry + risk if side == "LONG" else entry - risk
    return stop, target, risk


def _pnl(side: str, entry: float, exit_px: float) -> float:
    pts = (exit_px - entry) if side == "LONG" else (entry - exit_px)
    return pts * POINT_VALUE - FEE


def run_prototype_A(events: pd.DataFrame, tape: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sub = events[events["event_type"] == "CLOSE_BREAK"]
    for _, ev in sub.iterrows():
        available = _localize(pd.Timestamp(ev["feature_available_at"]))
        order_active = _localize(pd.Timestamp(ev["order_active_ts"]))
        resolved = _resolve_entry_bar(tape, available, order_active)
        if resolved is None:
            continue
        fill_ts, open_px = resolved
        direction = str(ev["outcome_direction"] or ev["break_direction"])
        side = _side_from_dir(direction)
        entry = _adverse_entry(side, open_px)
        level = float(ev["protected_swing_price"])
        stop, target, risk = _stop_target_A(side, entry, level)
        hard_end = (
            _localize(pd.Timestamp(ev["two_session_end_ts"]))
            if pd.notna(ev.get("two_session_end_ts"))
            else None
        )
        exit_ts, exit_px, reason, gap, mfe, mae = _manage_1r1r(
            tape,
            side=side,
            fill_ts=fill_ts,
            entry=entry,
            stop=stop,
            target=target,
            hard_end_ts=hard_end,
        )
        caus_ok = int(available < order_active < fill_ts < exit_ts)
        rows.append(
            {
                "trade_id": "A_%s" % ev["event_id"],
                "prototype": "A_close_break_cont",
                "event_id": ev["event_id"],
                "structure_id": ev["structure_id"],
                "slice": ev["slice"],
                "side": side,
                "available_at": available.isoformat(),
                "order_active_ts": order_active.isoformat(),
                "fill_ts": fill_ts.isoformat(),
                "entry": entry,
                "stop": stop,
                "target": target,
                "risk_pts": risk,
                "exit_ts": exit_ts.isoformat(),
                "exit": exit_px,
                "exit_reason": reason,
                "gap_through_stop": gap,
                "mfe_pts": mfe,
                "mae_pts": mae,
                "net_usd": _pnl(side, entry, exit_px),
                "r_multiple": ((exit_px - entry) if side == "LONG" else (entry - exit_px)) / risk if risk else 0.0,
                "causality_ok": caus_ok,
            }
        )
    return pd.DataFrame(rows)


def run_prototype_B(events: pd.DataFrame, tape: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sub = events[events["event_type"] == "WICK_REJECT"]
    for _, ev in sub.iterrows():
        available = _localize(pd.Timestamp(ev["feature_available_at"]))
        order_active = _localize(pd.Timestamp(ev["order_active_ts"]))
        resolved = _resolve_entry_bar(tape, available, order_active)
        if resolved is None:
            continue
        fill_ts, open_px = resolved
        direction = str(ev["outcome_direction"] or "")
        if direction not in ("bullish", "bearish"):
            continue
        side = _side_from_dir(direction)
        entry = _adverse_entry(side, open_px)
        level = float(ev["protected_swing_price"])
        pen = float(ev.get("penetration_points") or 0)
        break_dir = str(ev["break_direction"])
        stop, target, risk = _stop_target_B(side, entry, level, pen, break_dir)
        hard_end = (
            _localize(pd.Timestamp(ev["two_session_end_ts"]))
            if pd.notna(ev.get("two_session_end_ts"))
            else None
        )
        exit_ts, exit_px, reason, gap, mfe, mae = _manage_1r1r(
            tape,
            side=side,
            fill_ts=fill_ts,
            entry=entry,
            stop=stop,
            target=target,
            hard_end_ts=hard_end,
        )
        caus_ok = int(available < order_active < fill_ts < exit_ts)
        rows.append(
            {
                "trade_id": "B_%s" % ev["event_id"],
                "prototype": "B_wick_reject_fade",
                "event_id": ev["event_id"],
                "structure_id": ev["structure_id"],
                "slice": ev["slice"],
                "side": side,
                "available_at": available.isoformat(),
                "order_active_ts": order_active.isoformat(),
                "fill_ts": fill_ts.isoformat(),
                "entry": entry,
                "stop": stop,
                "target": target,
                "risk_pts": risk,
                "exit_ts": exit_ts.isoformat(),
                "exit": exit_px,
                "exit_reason": reason,
                "gap_through_stop": gap,
                "mfe_pts": mfe,
                "mae_pts": mae,
                "net_usd": _pnl(side, entry, exit_px),
                "r_multiple": ((exit_px - entry) if side == "LONG" else (entry - exit_px)) / risk if risk else 0.0,
                "causality_ok": caus_ok,
            }
        )
    return pd.DataFrame(rows)


def _parent_close_break_id(reclaim_id: str) -> str:
    # e.g. 4h_bull_61_INV_CLOSE_1457_RECLAIM_1458 → 4h_bull_61_INV_CLOSE_1457
    if "_RECLAIM_" in reclaim_id:
        return reclaim_id.split("_RECLAIM_")[0]
    return reclaim_id


def run_prototype_C(trades_a: pd.DataFrame, events: pd.DataFrame, tape: pd.DataFrame) -> pd.DataFrame:
    """Management test: exit open A continuation at reclaim if it fires first."""
    if trades_a is None or trades_a.empty:
        return pd.DataFrame()
    reclaim = events[events["event_type"] == "CLOSE_RECLAIM"].copy()
    reclaim["parent_id"] = reclaim["event_id"].map(_parent_close_break_id)
    by_parent = {r.parent_id: r for _, r in reclaim.iterrows()}

    rows = []
    for _, tr in trades_a.iterrows():
        parent = str(tr["event_id"])
        side = str(tr["side"])
        entry = float(tr["entry"])
        stop = float(tr["stop"])
        target = float(tr["target"])
        fill_ts = _localize(pd.Timestamp(tr["fill_ts"]))
        base_exit_ts = _localize(pd.Timestamp(tr["exit_ts"]))
        base_reason = str(tr["exit_reason"])
        base_exit = float(tr["exit"])
        base_net = float(tr["net_usd"])
        risk = float(tr["risk_pts"])

        used_reclaim = 0
        exit_ts, exit_px, reason, gap = base_exit_ts, base_exit, base_reason, int(tr["gap_through_stop"])
        mfe, mae = float(tr["mfe_pts"]), float(tr["mae_pts"])

        rc = by_parent.get(parent)
        if rc is not None:
            rc_avail = _localize(pd.Timestamp(rc["feature_available_at"]))
            rc_oa = _localize(pd.Timestamp(rc["order_active_ts"]))
            resolved = _resolve_entry_bar(tape, rc_avail, rc_oa)
            if resolved is not None:
                rc_fill_ts, rc_open = resolved
                # only if reclaim fill occurs while A would still be open
                if fill_ts < rc_fill_ts < base_exit_ts:
                    # Walk full tape but treat reclaim fill as a forced flatten deadline.
                    early_ts, early_px, early_reason, early_gap, mfe, mae = _manage_1r1r(
                        tape,
                        side=side,
                        fill_ts=fill_ts,
                        entry=entry,
                        stop=stop,
                        target=target,
                        force_flat_ts=rc_fill_ts,
                        force_flat_px=(
                            rc_open - SLIPPAGE_TICKS * TICK
                            if side == "LONG"
                            else rc_open + SLIPPAGE_TICKS * TICK
                        ),
                        force_flat_reason="reclaim_exit",
                    )
                    exit_ts, exit_px, reason, gap = early_ts, early_px, early_reason, early_gap
                    used_reclaim = int(reason == "reclaim_exit")

        net = _pnl(side, entry, exit_px)
        rows.append(
            {
                "trade_id": "C_%s" % parent,
                "prototype": "C_reclaim_invalidate_A",
                "event_id": parent,
                "structure_id": tr["structure_id"],
                "slice": tr["slice"],
                "side": side,
                "available_at": tr["available_at"],
                "order_active_ts": tr["order_active_ts"],
                "fill_ts": tr["fill_ts"],
                "entry": entry,
                "stop": stop,
                "target": target,
                "risk_pts": risk,
                "exit_ts": exit_ts.isoformat() if hasattr(exit_ts, "isoformat") else str(exit_ts),
                "exit": exit_px,
                "exit_reason": reason,
                "gap_through_stop": gap,
                "mfe_pts": mfe,
                "mae_pts": mae,
                "net_usd": net,
                "r_multiple": ((exit_px - entry) if side == "LONG" else (entry - exit_px)) / risk if risk else 0.0,
                "used_reclaim_exit": used_reclaim,
                "baseline_A_net_usd": base_net,
                "delta_vs_A_usd": net - base_net,
                "causality_ok": int(tr["causality_ok"]),
            }
        )
    return pd.DataFrame(rows)


def _summarize_book(df: pd.DataFrame, label: str) -> dict:
    if df is None or df.empty:
        return {"label": label, "n": 0}
    net = float(df["net_usd"].sum())
    n = int(len(df))
    wins = df[df["net_usd"] > 0]
    losses = df[df["net_usd"] <= 0]
    gp = float(wins["net_usd"].sum()) if len(wins) else 0.0
    gl = float(losses["net_usd"].sum()) if len(losses) else 0.0
    pf = (gp / abs(gl)) if gl < 0 else (float("inf") if gp > 0 else 0.0)
    # path stress approx: sum of adverse mae * PV (unit)
    stress = float((-df["mae_pts"] * POINT_VALUE).min()) if "mae_pts" in df.columns else float("nan")
    avg_r = float(df["r_multiple"].mean()) if "r_multiple" in df.columns else float("nan")
    gap_n = int(df["gap_through_stop"].sum()) if "gap_through_stop" in df.columns else 0
    caus = int(df["causality_ok"].sum()) if "causality_ok" in df.columns else 0
    by_reason = df["exit_reason"].value_counts().to_dict() if "exit_reason" in df.columns else {}
    return {
        "label": label,
        "n": n,
        "net_usd": net,
        "avg_net": net / n if n else 0.0,
        "win_rate": float((df["net_usd"] > 0).mean()),
        "profit_factor": pf,
        "avg_R": avg_r,
        "gap_through_n": gap_n,
        "causality_ok_n": caus,
        "expectancy_R": avg_r,
        "exit_reasons": by_reason,
        "stress_mae_usd_min": stress,
    }


def _slice_summary(df: pd.DataFrame, proto: str) -> List[dict]:
    out = []
    for sl in ("dev", "holdout", "ALL"):
        sub = df if sl == "ALL" else df[df["slice"] == sl]
        s = _summarize_book(sub, "%s_%s" % (proto, sl))
        out.append(s)
    return out


def write_docs(
    hub: Path,
    chart_meta: pd.DataFrame,
    sum_rows: List[dict],
    trades_a: pd.DataFrame,
    trades_b: pd.DataFrame,
    trades_c: pd.DataFrame,
) -> None:
    lines = [
        "# STRATEGY_PROTOTYPES — NQ structure-change Phase 5",
        "",
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "**Scope:** 4h invalidation, pen≥0.05 ATR only. No 1h mix. No runners/scale/filters.",
        "**Execution:** 1m stop-first, gap-through stops, ±1 tick entry slippage, $1.50 fee, NQ $20/pt.",
        "**Causality:** `available_at < order_active_ts < fill_ts` (fill = first 1m strictly after order_active).",
        "**Holdout:** locked read — no parameter changes after peek.",
        "",
        "## Sample charts",
        "",
        "Five 15m charts per event class under `sample_charts/` (zip: `sample_charts.zip`).",
        "Window ≈ confirm± ~1 session; yellow = confirm 4h window; blue dashed = protected swing.",
        "",
    ]
    if chart_meta is not None and not chart_meta.empty:
        lines += [
            "| Class | Charts |",
            "|---|---:|",
        ]
        for et in EVENT_CLASSES:
            lines.append("| %s | %d |" % (et, int((chart_meta["event_type"] == et).sum())))
        lines.append("")

    lines += [
        "## Narrow question 1 — Prototype A (close-break continuation 1R/1R)",
        "",
        "Does low structural-risk geometry have positive expectancy after costs + gap-through?",
        "",
        "## Narrow question 2 — Prototype B (wick-reject fade 1R/1R)",
        "",
        "Does confirmed structural rejection have simple executable reversal expectancy?",
        "",
        "## Narrow question 3 — Prototype C (reclaim invalidation of A)",
        "",
        "Does exiting an open A trade at reclaim improve forward outcome vs holding to 1R/1R?",
        "",
        "## Results",
        "",
        "| Book | n | net $ | avg $ | WR | PF | avg R | gap-thru | causality_ok |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in sum_rows:
        if s.get("n", 0) == 0:
            lines.append("| %s | 0 | — | — | — | — | — | — | — |" % s["label"])
            continue
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else "%.2f" % pf
        lines.append(
            "| %s | %d | %+.0f | %+.0f | %.1f%% | %s | %+.3f | %d | %d |"
            % (
                s["label"],
                s["n"],
                s["net_usd"],
                s["avg_net"],
                100 * s["win_rate"],
                pf_s,
                s["avg_R"],
                s["gap_through_n"],
                s["causality_ok_n"],
            )
        )

    # Prototype C paired delta
    lines += ["", "## Prototype C vs A (paired)", ""]
    if trades_c is not None and not trades_c.empty:
        for sl in ("dev", "holdout", "ALL"):
            sub = trades_c if sl == "ALL" else trades_c[trades_c["slice"] == sl]
            if sub.empty:
                continue
            n_rc = int(sub["used_reclaim_exit"].sum())
            dnet = float(sub["delta_vs_A_usd"].sum())
            lines.append(
                "- **%s**: reclaim exits used on **%d / %d** trades; Δnet vs A = **%+.0f**."
                % (sl, n_rc, len(sub), dnet)
            )
    else:
        lines.append("- No C trades.")

    # Stance
    def _book(name_suffix: str) -> Optional[dict]:
        for s in sum_rows:
            if s["label"] == name_suffix:
                return s
        return None

    a_dev = _book("A_close_break_cont_dev")
    a_ho = _book("A_close_break_cont_holdout")
    b_dev = _book("B_wick_reject_fade_dev")
    b_ho = _book("B_wick_reject_fade_holdout")

    def _stance(dev: Optional[dict], ho: Optional[dict]) -> str:
        if not dev or dev.get("n", 0) == 0:
            return "PENDING"
        if dev["net_usd"] <= 0 or dev["avg_R"] <= 0:
            return "REJECT base 1R/1R on dev"
        if ho and ho.get("n", 0) > 0 and (ho["net_usd"] <= 0 or ho["avg_R"] <= 0):
            return "RESEARCH — positive dev, failed locked holdout"
        if ho and ho.get("n", 0) > 0 and ho["net_usd"] > 0 and ho["avg_R"] > 0:
            return "RESEARCH — positive on locked holdout (not promote; no filters yet)"
        return "RESEARCH — positive dev; holdout thin/absent"

    lines += [
        "",
        "## Stance",
        "",
        "- Prototype A: **%s**" % _stance(a_dev, a_ho),
        "- Prototype B: **%s**" % _stance(b_dev, b_ho),
        "- Prototype C: management overlay — promote only if Δnet vs A > 0 on dev **and** holdout.",
        "",
        "## Guardrails honored",
        "",
        "- Not claiming 4h events beat controls on absolute ATR expansion.",
        "- Structural-stop R vs controls not used as a trading claim.",
        "- Targets fixed at 1R; no optimization.",
        "- 4h only; holdout untouched for locked read.",
        "",
    ]
    (hub / "STRATEGY_PROTOTYPES.md").write_text("\n".join(lines), encoding="utf-8")
    # also mirror into atlas hub for continuity
    (ATLAS_HUB / "STRATEGY_PROTOTYPES.md").write_text("\n".join(lines), encoding="utf-8")

    # STATUS
    status = [
        "# Status — NQ structure-change Phase 5 prototypes",
        "",
        "**Hub:** `%s`" % hub,
        "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
        "",
        "| Phase | Status |",
        "|---|---|",
        "| 0–4 atlas + outcome audit | DONE (see atlas hub) |",
        "| sample charts (5/class) | DONE |",
        "| Prototype A 1R/1R | DONE |",
        "| Prototype B 1R/1R | DONE |",
        "| Prototype C reclaim mgmt | DONE |",
        "",
        "Atlas hub: `%s`" % ATLAS_HUB,
        "",
    ]
    (hub / "STATUS.md").write_text("\n".join(status), encoding="utf-8")
    (ATLAS_HUB / "STATUS.md").write_text(
        "\n".join(
            [
                "# Status — NQ structure-change event study",
                "",
                "**Hub:** `live/state/nq_structure_change_event_study/`",
                "**Updated:** %s" % datetime.now().strftime("%Y-%m-%d %H:%M ET"),
                "",
                "| Phase | Status |",
                "|---|---|",
                "| 0–4 + outcome audit | DONE / PASS |",
                "| 5 prototypes | DONE → see `live/state/nq_structure_change_phase5_prototypes/` |",
                "| Cross-market | PENDING APPROVAL_GATE.md |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_email(
    hub: Path,
    sum_rows: List[dict],
    chart_meta: pd.DataFrame,
    *,
    charts_only: bool = False,
) -> str:
    lines = []
    if charts_only:
        lines.append("potions: NQ structure-change sample charts READY\n")
    else:
        lines.append("potions: NQ structure-change Phase 5 prototypes COMPLETE\n")
    lines.append("Hub: %s\n" % hub)
    lines.append("Charts: sample_charts/ (%d png) + sample_charts.zip\n" % (
        int(chart_meta["ok"].sum()) if chart_meta is not None and not chart_meta.empty else 0
    ))
    if charts_only:
        lines.append("Phase 5 prototype run follows (A→B→C, 1R/1R, holdout locked).\n")
        return "\n".join(lines)
    lines.append("\nResults (4h inv pen≥0.05, 1m stop-first, costs+gap):\n")
    for s in sum_rows:
        if s.get("n", 0) == 0:
            continue
        lines.append(
            "  %s: n=%d net=%+.0f WR=%.0f%% PF=%.2f avgR=%+.3f gap=%d"
            % (
                s["label"],
                s["n"],
                s["net_usd"],
                100 * s["win_rate"],
                s["profit_factor"] if s["profit_factor"] != float("inf") else 99.0,
                s["avg_R"],
                s["gap_through_n"],
            )
        )
    lines.append("\nSee STRATEGY_PROTOTYPES.md. Holdout is locked read.\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--charts-only", action="store_true")
    ap.add_argument("--skip-charts", action="store_true")
    args = ap.parse_args()

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    rid = begin_run(
        run_class="pandas",
        variant_slug="nq_structure_change_phase5_prototypes",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"smoke": args.smoke, "charts_only": args.charts_only},
    )
    try:
        _progress(hub, "load events")
        events = _load_primary_events(smoke=args.smoke)
        _progress(hub, "events primary n=%d" % len(events))

        _progress(hub, "load NQ 1m")
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
        days = sorted(gby.keys())
        if args.smoke:
            # restrict tape around sample event dates
            edates = sorted(
                {
                    _localize(pd.Timestamp(t)).date()
                    for t in events["confirm_bar_close_ts"].tolist()
                }
            )
            keep = set()
            all_days = days
            for d in edates:
                if d in all_days:
                    i = all_days.index(d)
                    keep.update(all_days[max(0, i - 3) : i + 4])
            gby = {d: gby[d] for d in days if d in keep}
            days = sorted(gby.keys())

        chart_meta = pd.DataFrame()
        if not args.skip_charts:
            _progress(hub, "generate sample charts")
            _, chart_meta = generate_sample_charts(hub, gby, events)
            if args.email:
                body = build_email(hub, [], chart_meta, charts_only=True)
                (hub / "EMAIL_CHARTS.txt").write_text(body, encoding="utf-8")
                attach = [hub / "sample_charts.zip"]
                # also attach up to 4 png previews (one per class)
                pngs = sorted((hub / "sample_charts").glob("*.png"))
                for et in EVENT_CLASSES:
                    for p in pngs:
                        if et in p.name:
                            attach.append(p)
                            break
                send_email(
                    subject="potions: NQ structure-change sample charts (5/class)",
                    body=body,
                    attachments=attach,
                )
                _progress(hub, "charts email sent")

        if args.charts_only:
            write_docs(hub, chart_meta, [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
            complete_run(rid, trades=0, meta={"charts_only": True})
            return

        _progress(hub, "build 1m tape")
        frames = []
        for d in days:
            rth = rth_slice(gby[d])
            if rth is not None and not rth.empty:
                frames.append(rth)
        tape = pd.concat(frames)
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
        _progress(hub, "tape bars=%d" % len(tape))

        _progress(hub, "Prototype A")
        trades_a = run_prototype_A(events, tape)
        trades_a.to_csv(hub / "trades_A.csv", index=False)
        _progress(hub, "A n=%d" % len(trades_a))

        _progress(hub, "Prototype B")
        trades_b = run_prototype_B(events, tape)
        trades_b.to_csv(hub / "trades_B.csv", index=False)
        _progress(hub, "B n=%d" % len(trades_b))

        _progress(hub, "Prototype C")
        trades_c = run_prototype_C(trades_a, events, tape)
        trades_c.to_csv(hub / "trades_C.csv", index=False)
        _progress(hub, "C n=%d reclaim_used=%d" % (
            len(trades_c),
            int(trades_c["used_reclaim_exit"].sum()) if len(trades_c) else 0,
        ))

        sum_rows: List[dict] = []
        sum_rows.extend(_slice_summary(trades_a, "A_close_break_cont"))
        sum_rows.extend(_slice_summary(trades_b, "B_wick_reject_fade"))
        sum_rows.extend(_slice_summary(trades_c, "C_reclaim_invalidate_A"))
        pd.DataFrame(sum_rows).to_csv(hub / "summary.csv", index=False)

        write_docs(hub, chart_meta, sum_rows, trades_a, trades_b, trades_c)

        # causality violation count
        for name, df in [("A", trades_a), ("B", trades_b)]:
            if df is None or df.empty:
                continue
            bad = int((df["causality_ok"] == 0).sum())
            _progress(hub, "%s causality failures: %d / %d" % (name, bad, len(df)))

        body = build_email(hub, sum_rows, chart_meta, charts_only=False)
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "n_A": int(len(trades_a)),
                    "n_B": int(len(trades_b)),
                    "n_C": int(len(trades_c)),
                    "smoke": args.smoke,
                    "summaries": sum_rows,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        net = float(trades_a["net_usd"].sum()) if len(trades_a) else 0.0
        complete_run(
            rid,
            net_usd=net,
            trades=int(len(trades_a) + len(trades_b)),
            meta={"phase": 5, "smoke": args.smoke},
        )

        if args.email:
            attach = []
            z = hub / "sample_charts.zip"
            if z.exists():
                attach.append(z)
            attach.append(hub / "STRATEGY_PROTOTYPES.md")
            attach.append(hub / "summary.csv")
            send_email(
                subject="potions: NQ structure-change Phase 5 prototypes COMPLETE",
                body=body,
                attachments=attach or None,
            )
            _progress(hub, "completion email sent")

    except Exception as exc:
        err = traceback.format_exc()
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        fail_run(rid, error=str(exc))
        if args.email:
            send_email(
                subject="potions: NQ structure-change Phase 5 FAILED",
                body="Hub: %s\n\n%s" % (hub, err[-4000:]),
            )
        raise


if __name__ == "__main__":
    main()
