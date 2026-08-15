"""Bias-change candle as v2b-style opening range (OCO breakout).

The 1h candle that prints a 15m program/bias flip defines an OR:
  OR high / OR low = that candle's high / low
  R = OR high − OR low

**Arming:** OCO stop orders arm at **09:30** RTH only (each session while the
bias OR still has attempts left).

**Fills:** trade-through only — overnight / open **gaps through** a boundary
do **not** fill. Price must come back to the valid side of the level, then
trade through it during the session to trigger the stop.

Sizing **1/1/2/1** (5ct):
  1 @ +1R · 1 @ +2R · 2 @ EOD · 1 runner @ 20R (may span days/weeks).
After TP1, remaining stop → BE. Multiple day-spanning runners may stack.
**2 attempts** per bias-change candle.

Usage:
  python -m live.structure_program_st_bias_or_oco --start 2020-01-01 --n-charts 50
"""

from __future__ import annotations

import argparse
import random
from dataclasses import asdict, dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .structure_program_st_study import (
    FEE_PER_CONTRACT_RT,
    POINT_VALUE,
    StructureProgramEngine,
    confirm_swings,
    rth_slice,
    to_15m,
    try_form_structures,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st" / "bias_or_oco"
NY = "America/New_York"
RTH_OPEN = time(9, 30)

ENTRY_QTY = 5
TP1_QTY = 1
TP2_QTY = 1
EOD_QTY = 2
RUNNER_QTY = 1
RUNNER_R = 20.0
MAX_ATTEMPTS = 2
N_CHART_EACH = 50


@dataclass
class BiasOR:
    flip_ts: pd.Timestamp
    program: str
    high: float
    low: float
    bar_ts: pd.Timestamp
    R: float
    attempts_used: int = 0
    active: bool = True
    # after a gap-through, side stays blocked until price reclaims into range
    long_blocked: bool = False
    short_blocked: bool = False


@dataclass
class Position:
    """Intraday book for one OCO attempt (includes eod bucket + pending runner)."""

    trade_id: int
    side: str
    entry: float
    entry_ts: pd.Timestamp
    stop: float
    R: float
    or_high: float
    or_low: float
    attempt: int
    bias_flip_ts: pd.Timestamp
    qty_open: float = float(ENTRY_QTY)
    qty_tp1: float = float(TP1_QTY)
    qty_tp2: float = float(TP2_QTY)
    qty_eod: float = float(EOD_QTY)
    qty_runner: float = float(RUNNER_QTY)
    hit_tp1: bool = False
    hit_tp2: bool = False
    be_armed: bool = False
    realized_usd: float = 0.0
    exit_legs: List[str] = field(default_factory=list)
    mfe_pts: float = 0.0
    mae_pts: float = 0.0


@dataclass
class RunnerLot:
    """Day-spanning 1ct runner (20R); multiple may be open at once."""

    trade_id: int
    side: str
    entry: float
    entry_ts: pd.Timestamp
    stop: float  # BE
    R: float
    target: float
    or_high: float
    or_low: float
    attempt: int
    bias_flip_ts: pd.Timestamp
    parent_legs: str = ""
    realized_usd: float = 0.0
    mfe_pts: float = 0.0
    mae_pts: float = 0.0


@dataclass
class TradeRow:
    trade_id: int
    side: str
    attempt: int
    kind: str  # day | runner
    bias_flip_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    or_high: float
    or_low: float
    R: float
    stop0: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    pnl_usd: float
    qty: float
    hit_tp1: bool
    hit_tp2: bool
    be_armed: bool
    mfe_pts: float
    mae_pts: float


def to_1h(rth_1m: pd.DataFrame) -> pd.DataFrame:
    if rth_1m is None or rth_1m.empty:
        return pd.DataFrame()
    ohlc = rth_1m.resample("1h", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in rth_1m.columns else ("close", "count"),
    )
    return ohlc.dropna(subset=["open", "high", "low", "close"])


def _bias_candle_1h(day_1h: pd.DataFrame, flip_ts: pd.Timestamp) -> Optional[Tuple[float, float, pd.Timestamp]]:
    ts = pd.Timestamp(flip_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    if day_1h is None or day_1h.empty:
        return None
    for bt, row in day_1h.iterrows():
        if bt <= ts < bt + pd.Timedelta(hours=1):
            return float(row["high"]), float(row["low"]), bt
    deltas = [(abs((bt - ts).total_seconds()), bt, row) for bt, row in day_1h.iterrows()]
    if not deltas:
        return None
    _, bt, row = min(deltas, key=lambda t: t[0])
    return float(row["high"]), float(row["low"]), bt


def _realize_pos(pos: Position, qty: float, px: float, tag: str) -> None:
    qty = min(qty, pos.qty_open)
    if qty <= 0:
        return
    sign = 1.0 if pos.side == "long" else -1.0
    pts = sign * (px - pos.entry)
    pos.realized_usd += pts * qty * POINT_VALUE - FEE_PER_CONTRACT_RT * qty
    pos.qty_open -= qty
    pos.exit_legs.append(tag)


def _trade_from_pos(pos: Position, ts: pd.Timestamp, px: float, reason: str, qty_closed: float) -> TradeRow:
    if pos.qty_open > 0 and reason not in {"runner_spin"}:
        _realize_pos(pos, pos.qty_open, px, reason)
    legs = "+".join(pos.exit_legs) if pos.exit_legs else reason
    return TradeRow(
        trade_id=pos.trade_id,
        side=pos.side,
        attempt=pos.attempt,
        kind="day",
        bias_flip_ts=pos.bias_flip_ts,
        entry_ts=pos.entry_ts,
        entry=pos.entry,
        or_high=pos.or_high,
        or_low=pos.or_low,
        R=pos.R,
        stop0=pos.or_low if pos.side == "long" else pos.or_high,
        exit_ts=ts,
        exit=px,
        exit_reason=legs,
        pnl_usd=pos.realized_usd,
        qty=qty_closed,
        hit_tp1=pos.hit_tp1,
        hit_tp2=pos.hit_tp2,
        be_armed=pos.be_armed,
        mfe_pts=pos.mfe_pts,
        mae_pts=pos.mae_pts,
    )


def _trade_from_runner(r: RunnerLot, ts: pd.Timestamp, px: float, tag: str) -> TradeRow:
    sign = 1.0 if r.side == "long" else -1.0
    pts = sign * (px - r.entry)
    pnl = pts * POINT_VALUE - FEE_PER_CONTRACT_RT
    legs = (r.parent_legs + "+" + tag) if r.parent_legs else tag
    return TradeRow(
        trade_id=r.trade_id,
        side=r.side,
        attempt=r.attempt,
        kind="runner",
        bias_flip_ts=r.bias_flip_ts,
        entry_ts=r.entry_ts,
        entry=r.entry,
        or_high=r.or_high,
        or_low=r.or_low,
        R=r.R,
        stop0=r.entry,
        exit_ts=ts,
        exit=px,
        exit_reason=legs,
        pnl_usd=pnl,
        qty=1.0,
        hit_tp1=True,
        hit_tp2="tp2" in (r.parent_legs or ""),
        be_armed=True,
        mfe_pts=r.mfe_pts,
        mae_pts=r.mae_pts,
    )


def _eod_close_day_pos(
    pos: Position,
    ts: pd.Timestamp,
    c: float,
    runners: List[RunnerLot],
    trades: List[TradeRow],
) -> None:
    """Flatten day book at session end; spin 1ct runner if designated."""
    sign = 1.0 if pos.side == "long" else -1.0
    if pos.qty_runner > 0 and pos.qty_open >= 1.0:
        flat_q = pos.qty_open - 1.0
        if flat_q > 0:
            _realize_pos(pos, flat_q, c, "eod")
        runners.append(
            RunnerLot(
                trade_id=pos.trade_id,
                side=pos.side,
                entry=pos.entry,
                entry_ts=pos.entry_ts,
                stop=pos.entry if pos.be_armed else pos.stop,
                R=pos.R,
                target=pos.entry + sign * RUNNER_R * pos.R,
                or_high=pos.or_high,
                or_low=pos.or_low,
                attempt=pos.attempt,
                bias_flip_ts=pos.bias_flip_ts,
                parent_legs="+".join(pos.exit_legs),
                mfe_pts=pos.mfe_pts,
                mae_pts=pos.mae_pts,
            )
        )
        pos.qty_open = 0.0
        pos.qty_runner = 0.0
        pos.qty_eod = 0.0
        pos.exit_legs.append("runner_spin")
    elif pos.qty_open > 0:
        _realize_pos(pos, pos.qty_open, c, "eod")
        pos.qty_eod = 0.0
    trades.append(
        TradeRow(
            trade_id=pos.trade_id,
            side=pos.side,
            attempt=pos.attempt,
            kind="day",
            bias_flip_ts=pos.bias_flip_ts,
            entry_ts=pos.entry_ts,
            entry=pos.entry,
            or_high=pos.or_high,
            or_low=pos.or_low,
            R=pos.R,
            stop0=pos.or_low if pos.side == "long" else pos.or_high,
            exit_ts=ts,
            exit=c,
            exit_reason="+".join(pos.exit_legs) if pos.exit_legs else "eod",
            pnl_usd=pos.realized_usd,
            qty=float(ENTRY_QTY - RUNNER_QTY) if "runner_spin" in pos.exit_legs else float(ENTRY_QTY),
            hit_tp1=pos.hit_tp1,
            hit_tp2=pos.hit_tp2,
            be_armed=pos.be_armed,
            mfe_pts=pos.mfe_pts,
            mae_pts=pos.mae_pts,
        )
    )


def _update_mfe_mae_side(side: str, entry: float, h: float, l: float, mfe: float, mae: float) -> Tuple[float, float]:
    if side == "long":
        return max(mfe, h - entry), max(mae, entry - l)
    return max(mfe, entry - l), max(mae, h - entry)


def _trade_through_long(o: float, h: float, level: float) -> bool:
    """Buy stop: open not already through; high trades through."""
    return o <= level and h >= level


def _trade_through_short(o: float, l: float, level: float) -> bool:
    """Sell stop: open not already through; low trades through."""
    return o >= level and l <= level


def _update_gap_blocks(bias_or: BiasOR, o: float, h: float, l: float, c: float) -> None:
    """Block sides that gap through; unblock when price reclaims into the OR."""
    # gap through high → block long until reclaim (trade back to <= high)
    if o > bias_or.high:
        bias_or.long_blocked = True
    if bias_or.long_blocked and (l <= bias_or.high or c <= bias_or.high):
        bias_or.long_blocked = False
    # gap through low → block short until reclaim (>= low)
    if o < bias_or.low:
        bias_or.short_blocked = True
    if bias_or.short_blocked and (h >= bias_or.low or c >= bias_or.low):
        bias_or.short_blocked = False


def run_study(
    start: Optional[date] = None,
    end: Optional[date] = None,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
) -> pd.DataFrame:
    if gby is None:
        print("Loading NQ 1m…", flush=True)
        gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    eng = StructureProgramEngine()
    bias_or: Optional[BiasOR] = None
    oco_armed = False
    pos: Optional[Position] = None
    runners: List[RunnerLot] = []
    trades: List[TradeRow] = []
    next_id = 1

    print("Running bias_or_oco (1/1/2/1, 09:30 arm, trade-through) over %d days…" % len(days), flush=True)
    n_arm = n_flip = n_fill_try = 0
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b15 = to_15m(rth)
        b1h = to_1h(rth)
        if b1h.empty:
            continue

        day_swings = confirm_swings(b15)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            by_confirm.setdefault(sw[0], []).append(sw)

        flips_by_1h: Dict[pd.Timestamp, BiasOR] = {}
        for ts, row in b15.iterrows():
            for sw in by_confirm.get(ts, []):
                if eng.swings and eng.swings[-1][1] == sw[1]:
                    prev = eng.swings[-1]
                    if sw[1] == "H" and sw[2] >= prev[2]:
                        eng.swings[-1] = sw
                    elif sw[1] == "L" and sw[2] <= prev[2]:
                        eng.swings[-1] = sw
                    else:
                        continue
                else:
                    eng.swings.append(sw)
                for st in try_form_structures(eng.swings):
                    sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                    if sig in eng._seen_structure_keys:
                        continue
                    eng._seen_structure_keys.add(sig)
                    if st.kind == "bull":
                        eng.bull.append(st)
                    else:
                        eng.bear.append(st)
            prev_prog = eng.program
            eng._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
            if eng.program in {"buy", "sell"} and eng.program != prev_prog and eng.ready:
                candle = _bias_candle_1h(b1h, ts)
                if candle is None:
                    continue
                hi, lo, bt = candle
                R = hi - lo
                if R < 1.0:
                    continue
                flips_by_1h[bt] = BiasOR(
                    flip_ts=ts, program=eng.program, high=hi, low=lo, bar_ts=bt, R=R
                )

        # --- session-open arm: first RTH 1h bar (label may be 09:00 with 1h resample) ---
        first_ts = b1h.index[0]
        if (
            bias_or is not None
            and bias_or.active
            and bias_or.attempts_used < MAX_ATTEMPTS
            and pos is None
            and bias_or.bar_ts < first_ts
        ):
            oco_armed = True
            bias_or.long_blocked = False
            bias_or.short_blocked = False
            n_arm += 1

        for bi, (ts, row) in enumerate(b1h.iterrows()):
            o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
            is_last = bi == len(b1h) - 1

            # new bias OR on this completed 1h bar → wait until next session open to arm
            if ts in flips_by_1h:
                bias_or = flips_by_1h[ts]
                oco_armed = False
                n_flip += 1

            # --- manage stacked runners every bar ---
            still_runners: List[RunnerLot] = []
            for r in runners:
                r.mfe_pts, r.mae_pts = _update_mfe_mae_side(r.side, r.entry, h, l, r.mfe_pts, r.mae_pts)
                hit_stop = (r.side == "long" and l <= r.stop) or (r.side == "short" and h >= r.stop)
                hit_tgt = (r.side == "long" and h >= r.target) or (r.side == "short" and l <= r.target)
                if hit_stop:
                    trades.append(_trade_from_runner(r, ts, float(r.stop), "be_stop"))
                elif hit_tgt:
                    trades.append(_trade_from_runner(r, ts, float(r.target), "runner_20R"))
                else:
                    still_runners.append(r)
            runners = still_runners

            # --- manage day position ---
            if pos is not None:
                pos.mfe_pts, pos.mae_pts = _update_mfe_mae_side(
                    pos.side, pos.entry, h, l, pos.mfe_pts, pos.mae_pts
                )
                sign = 1.0 if pos.side == "long" else -1.0
                hit_stop = (pos.side == "long" and l <= pos.stop) or (
                    pos.side == "short" and h >= pos.stop
                )
                if hit_stop:
                    tag = "be_stop" if pos.be_armed else "or_stop"
                    closed_qty = float(ENTRY_QTY)
                    trades.append(_trade_from_pos(pos, ts, float(pos.stop), tag, closed_qty))
                    pos = None
                    # next attempt only arms at a subsequent 09:30
                    oco_armed = False

                if pos is not None and not pos.hit_tp1 and pos.qty_tp1 > 0:
                    tp1 = pos.entry + sign * pos.R
                    if (pos.side == "long" and h >= tp1) or (pos.side == "short" and l <= tp1):
                        _realize_pos(pos, pos.qty_tp1, tp1, "tp1")
                        pos.hit_tp1 = True
                        pos.qty_tp1 = 0.0
                        pos.stop = pos.entry
                        pos.be_armed = True

                if pos is not None and pos.hit_tp1 and not pos.hit_tp2 and pos.qty_tp2 > 0:
                    tp2 = pos.entry + sign * 2.0 * pos.R
                    if (pos.side == "long" and h >= tp2) or (pos.side == "short" and l <= tp2):
                        _realize_pos(pos, pos.qty_tp2, tp2, "tp2")
                        pos.hit_tp2 = True
                        pos.qty_tp2 = 0.0

                # EOD: flatten all but 1ct runner (stackable, targets 20R)
                if pos is not None and is_last:
                    _eod_close_day_pos(pos, ts, c, runners, trades)
                    pos = None

            # --- OCO: update gap blocks + trade-through fills ---
            if bias_or is not None and bias_or.active and oco_armed and pos is None:
                _update_gap_blocks(bias_or, o, h, l, c)

                long_ok = (not bias_or.long_blocked) and _trade_through_long(o, h, bias_or.high)
                short_ok = (not bias_or.short_blocked) and _trade_through_short(o, l, bias_or.low)

                side = fill = None
                if long_ok and short_ok:
                    # both trade-through same bar — pick nearer to open
                    if abs(o - bias_or.high) <= abs(o - bias_or.low):
                        side, fill = "long", bias_or.high
                    else:
                        side, fill = "short", bias_or.low
                elif long_ok:
                    side, fill = "long", bias_or.high
                elif short_ok:
                    side, fill = "short", bias_or.low

                if side is not None:
                    n_fill_try += 1
                    bias_or.attempts_used += 1
                    oco_armed = False
                    stop = bias_or.low if side == "long" else bias_or.high
                    pos = Position(
                        trade_id=next_id,
                        side=side,
                        entry=float(fill),
                        entry_ts=ts,
                        stop=float(stop),
                        R=float(bias_or.R),
                        or_high=float(bias_or.high),
                        or_low=float(bias_or.low),
                        attempt=int(bias_or.attempts_used),
                        bias_flip_ts=bias_or.flip_ts,
                    )
                    next_id += 1
                    if bias_or.attempts_used >= MAX_ATTEMPTS:
                        bias_or.active = False
                    # same-bar manage after fill
                    pos.mfe_pts, pos.mae_pts = _update_mfe_mae_side(side, pos.entry, h, l, 0.0, 0.0)
                    hit_stop = (side == "long" and l <= pos.stop) or (side == "short" and h >= pos.stop)
                    if hit_stop:
                        trades.append(_trade_from_pos(pos, ts, float(pos.stop), "or_stop", float(ENTRY_QTY)))
                        pos = None
                        oco_armed = False
                    else:
                        sign = 1.0 if side == "long" else -1.0
                        tp1 = pos.entry + sign * pos.R
                        if (side == "long" and h >= tp1) or (side == "short" and l <= tp1):
                            _realize_pos(pos, pos.qty_tp1, tp1, "tp1")
                            pos.hit_tp1 = True
                            pos.qty_tp1 = 0.0
                            pos.stop = pos.entry
                            pos.be_armed = True
                            tp2 = pos.entry + sign * 2.0 * pos.R
                            if (side == "long" and h >= tp2) or (side == "short" and l <= tp2):
                                _realize_pos(pos, pos.qty_tp2, tp2, "tp2")
                                pos.hit_tp2 = True
                                pos.qty_tp2 = 0.0
                        if is_last and pos is not None:
                            _eod_close_day_pos(pos, ts, c, runners, trades)
                            pos = None

            # disarm OCO at session end if unfilled
            if is_last:
                oco_armed = False

        if di % 250 == 0:
            print(
                "  %d/%d days | trades %d | runners %d | arms=%d flips=%d fills=%d | attempts=%s oco=%s open=%s"
                % (
                    di,
                    len(days),
                    len(trades),
                    len(runners),
                    n_arm,
                    n_flip,
                    n_fill_try,
                    bias_or.attempts_used if bias_or else None,
                    oco_armed,
                    pos is not None,
                ),
                flush=True,
            )

    print(
        "Done counters: arms=%d flips=%d fill_tries=%d trades=%d runners_left=%d"
        % (n_arm, n_flip, n_fill_try, len(trades), len(runners)),
        flush=True,
    )

    # flatten residual day pos + runners at end
    if pos is not None:
        trades.append(_trade_from_pos(pos, pos.entry_ts, pos.entry, "eod_residual", float(pos.qty_open or ENTRY_QTY)))
    for r in runners:
        trades.append(_trade_from_runner(r, r.entry_ts, r.entry, "eod_residual"))

    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in trades])
    if not df.empty:
        df.to_csv(OUT / "trades.csv", index=False)
    _write_summary(df)
    print("Wrote %d trades → %s" % (len(df), OUT), flush=True)
    return df


def _write_summary(df: pd.DataFrame) -> None:
    lines = [
        "# Bias-candle OR OCO (1/1/2/1, 09:30 arm, trade-through)",
        "",
        "Bias-change 1h candle = OR. OCO stops arm at **09:30** only. "
        "**No gap-through fills** — must trade through the boundary (reclaim+rebreak "
        "if gapped). Sizing **1/1/2/1**: 1@1R · 1@2R · 2@EOD · 1 runner@20R (stackable). "
        "**2 attempts** per bias candle.",
        "",
    ]
    if df is None or df.empty:
        lines.append("No trades.")
        (OUT / "SUMMARY.md").write_text("\n".join(lines))
        return
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    gp = float(wins.pnl_usd.sum()) if len(wins) else 0.0
    gl = float(-losses.pnl_usd.sum()) if len(losses) else 1e-9
    pf = gp / gl if gl > 0 else float("inf")
    day = df[df.kind == "day"] if "kind" in df.columns else df
    run = df[df.kind == "runner"] if "kind" in df.columns else df.iloc[0:0]
    lines += [
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        "| trades | %d |" % len(df),
        "| day / runner rows | %d / %d |" % (len(day), len(run)),
        "| net $ | %.0f |" % df.pnl_usd.sum(),
        "| win%% | %.1f |" % (100.0 * (df.pnl_usd > 0).mean()),
        "| PF | %.3f |" % pf,
        "| avg $/trade | %.1f |" % df.pnl_usd.mean(),
        "| long / short | %d / %d |"
        % (int((df.side == "long").sum()), int((df.side == "short").sum())),
        "| attempt 1 / 2 | %d / %d |"
        % (int((df.attempt == 1).sum()), int((df.attempt == 2).sum())),
        "| hit_tp1 / tp2 | %d / %d |" % (int(df.hit_tp1.sum()), int(df.hit_tp2.sum())),
        "",
        "### By kind",
        "",
        df.groupby("kind").pnl_usd.agg(["count", "sum", "mean"]).to_markdown()
        if "kind" in df.columns
        else "",
        "",
        "### By exit reason",
        "",
        df.groupby("exit_reason").pnl_usd.agg(["count", "sum", "mean"]).to_markdown(),
        "",
        "### By year",
        "",
    ]
    yr = df.copy()
    yr["year"] = pd.to_datetime(yr["entry_ts"], utc=True).dt.tz_convert(NY).dt.year
    lines.append(yr.groupby("year").pnl_usd.agg(["count", "sum", "mean"]).to_markdown())
    lines += [
        "",
        "### By attempt",
        "",
        df.groupby("attempt").pnl_usd.agg(["count", "sum", "mean"]).to_markdown(),
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


def chart_trades(gby, df: pd.DataFrame, n_each: int = N_CHART_EACH, seed: int = 42) -> None:
    if df is None or df.empty:
        return
    # chart day campaigns primarily (richer geometry); include runners if needed
    base = df[df.kind == "day"] if "kind" in df.columns else df
    if len(base) < n_each:
        base = df
    rng = random.Random(seed)
    wins = base[base.pnl_usd > 0]
    losses = base[base.pnl_usd <= 0]

    def pick(sub, k):
        if sub.empty:
            return sub
        idxs = sub.index.tolist()
        if len(idxs) <= k:
            return sub.copy()
        step = max(1, len(idxs) // k)
        chosen = idxs[::step][:k]
        if len(chosen) < k:
            rest = [i for i in idxs if i not in set(chosen)]
            chosen.extend(rng.sample(rest, min(k - len(chosen), len(rest))))
        return sub.loc[chosen[:k]].copy()

    sample = pd.concat([pick(wins, n_each), pick(losses, n_each)]).sort_values("entry_ts")
    win_dir = OUT / "charts" / "winners"
    loss_dir = OUT / "charts" / "losers"
    for d in (win_dir, loss_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.png"):
            old.unlink()

    print("Charting %d trades…" % len(sample), flush=True)
    wi = li = 0
    rows = []
    for _, t in sample.iterrows():
        is_win = float(t.pnl_usd) > 0
        if is_win:
            wi += 1
            cid, out_dir = wi, win_dir
        else:
            li += 1
            cid, out_dir = li, loss_dir
        if _plot_one(gby, t, out_dir, cid):
            rows.append(
                {
                    "chart_id": cid,
                    "result": "win" if is_win else "loss",
                    "trade_id": t.trade_id,
                    "pnl_usd": t.pnl_usd,
                    "attempt": t.attempt,
                    "side": t.side,
                    "kind": t.get("kind", "day") if hasattr(t, "get") else t.kind,
                    "exit_reason": t.exit_reason,
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "charts" / "charted.csv", index=False)
    (OUT / "charts" / "README.md").write_text(
        "# Bias-OR OCO charts\n\n%d winners + %d losers.\n"
        "OR = bias 1h H/L; 09:30 arm; trade-through only; 1/1/2/1.\n" % (wi, li)
    )
    print("Charts → %s" % (OUT / "charts"), flush=True)


def _plot_one(gby, t: pd.Series, out_dir: Path, cid: int) -> bool:
    entry_ts = pd.Timestamp(t.entry_ts)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize(NY)
    else:
        entry_ts = entry_ts.tz_convert(NY)
    exit_ts = pd.Timestamp(t.exit_ts)
    if exit_ts.tzinfo is None:
        exit_ts = exit_ts.tz_localize(NY)
    else:
        exit_ts = exit_ts.tz_convert(NY)
    d0 = entry_ts.date()
    all_days = sorted(gby)
    if d0 not in all_days:
        near = [d for d in all_days if abs((d - d0).days) < 5]
        if not near:
            return False
        d0 = min(near, key=lambda x: abs((x - d0).days))
    i0 = all_days.index(d0)
    end_i = all_days.index(exit_ts.date()) if exit_ts.date() in all_days else i0
    end_i = max(end_i, i0)
    sessions = all_days[max(0, i0 - 1) : min(len(all_days), end_i + 2)]
    frames = []
    for d in sessions:
        rth = rth_slice(gby[d])
        if rth.empty:
            continue
        h1 = to_1h(rth)
        if not h1.empty:
            frames.append(h1)
    if not frames:
        return False
    plot = pd.concat(frames).sort_index()
    plot = plot[~plot.index.duplicated(keep="last")]
    if len(plot) < 5:
        return False

    fig, ax = plt.subplots(figsize=(16, 8))
    x = np.arange(len(plot))
    o, h, l, c = [plot[k].to_numpy() for k in ("open", "high", "low", "close")]
    up = c >= o
    ax.vlines(x, l, h, color="#888", lw=0.8, zorder=1)
    ax.vlines(x[up], o[up], c[up], color="#1a9850", lw=2.0, zorder=2)
    ax.vlines(x[~up], c[~up], o[~up], color="#d73027", lw=2.0, zorder=2)

    rh, rl, R = float(t.or_high), float(t.or_low), float(t.R)
    ax.axhspan(rl, rh, color="#ffe082", alpha=0.25, zorder=0, label="bias OR")
    ax.axhline(rh, color="#f9a825", lw=1.6, label="OR high (buy stop)")
    ax.axhline(rl, color="#f9a825", lw=1.6, label="OR low (sell stop)")
    sign = 1.0 if t.side == "long" else -1.0
    e = float(t.entry)
    ax.axhline(e + sign * R, color="#2e7d32", lw=1.0, ls="--", label="TP1 1R")
    ax.axhline(e + sign * 2 * R, color="#1b5e20", lw=1.0, ls="--", label="TP2 2R")
    ax.axhline(e + sign * RUNNER_R * R, color="#004d40", lw=0.9, ls=":", label="runner 20R")

    def xi(ts):
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize(NY)
        else:
            ts = ts.tz_convert(NY)
        for i, bt in enumerate(plot.index):
            if bt <= ts < bt + pd.Timedelta(hours=1):
                return i
        deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(plot.index)]
        return min(deltas)[1] if deltas else None

    ei, xi_ = xi(entry_ts), xi(exit_ts)
    color = "#1a9850" if float(t.pnl_usd) > 0 else "#d73027"
    if ei is not None:
        ax.scatter(
            [ei],
            [e],
            marker="^" if t.side == "long" else "v",
            s=160,
            color=color,
            edgecolors="white",
            zorder=8,
        )
    if xi_ is not None:
        ax.scatter([xi_], [float(t.exit)], marker="X", s=140, color=color, edgecolors="white", zorder=8)

    kind = str(t.kind) if "kind" in t.index else "day"
    tag = "WIN" if float(t.pnl_usd) > 0 else "LOSS"
    ax.set_title(
        "NQ 1h bias-OR OCO #%d %s %s $%+.0f | %s a%d | %s → %s | %s"
        % (
            cid,
            str(t.side).upper(),
            tag,
            float(t.pnl_usd),
            kind,
            int(t.attempt),
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%m-%d %H:%M"),
            t.exit_reason,
        ),
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=7)
    ax.set_xlim(-1, len(plot))
    step = max(1, len(plot) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(
        [plot.index[i].strftime("%m-%d %H:%M") for i in x[::step]],
        rotation=30,
        ha="right",
        fontsize=8,
    )
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fname = "%03d_%s_%s_a%d_pnl%+.0f.png" % (
        cid,
        entry_ts.strftime("%Y-%m-%d"),
        t.side,
        int(t.attempt),
        float(t.pnl_usd),
    )
    fig.savefig(out_dir / fname, dpi=110)
    plt.close(fig)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--charts-only", action="store_true")
    ap.add_argument("--n-charts", type=int, default=N_CHART_EACH)
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    if args.charts_only:
        df = pd.read_csv(OUT / "trades.csv")
    else:
        df = run_study(start=start, end=end, gby=gby)
    if df is not None and not df.empty:
        chart_trades(gby, df, n_each=args.n_charts)


if __name__ == "__main__":
    main()
