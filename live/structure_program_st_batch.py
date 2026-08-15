"""Batch risk sweeps + cross-market runs for structure-program ST.

Plans:
  scale4  — 4ct; 2@1R → BE; 2 runners @3R (or ST flip)
  split15 — 15ct; 5@1R → BE; 5@EOD; 5@6R (no ST flip after scale)

Usage:
  python -m live.structure_program_st_batch --market nq --plan scale4 --risks 8,10,12,16,20
  python -m live.structure_program_st_batch --market nq --plan split15 --risks 8,10,12,16,20
  python -m live.structure_program_st_batch --markets nq mnq ym es eurusd_ny usdjpy_ny us30 nas100 xauusd_ny \\
      --plan <best> --risks <best>
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_or_markets import FX_MARKETS, load_market_gby, session_bars
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    LIST_SIZE,
    NY,
    OUT_ROOT,
    STRUCTURE_SL_PENDING_MAX_CLOSES,
    StructureProgramEngine,
    Trade,
    _md_agg,
    _write_mae_profile,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]

# Futures point values / fees (1 contract round-turn estimate)
FUT_SPECS = {
    "nq": {"point_value": 20.0, "fee_rt": 3.0, "label": "NQ"},
    "mnq": {"point_value": 2.0, "fee_rt": 1.24, "label": "MNQ"},
    "ym": {"point_value": 5.0, "fee_rt": 3.0, "label": "YM"},
    "es": {"point_value": 50.0, "fee_rt": 3.0, "label": "ES"},
}


@dataclass(frozen=True)
class Plan:
    name: str
    entry_qty: int
    off_1r: int
    eod_qty: int
    runner_qty: int
    runner_r: float
    st_flip_after_scale: bool


PLANS = {
    "scale4": Plan("scale4", 4, 2, 0, 2, 3.0, True),
    "split15": Plan("split15", 15, 5, 5, 5, 6.0, False),
}


def _rth_fut(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize(NY)
    else:
        out.index = out.index.tz_convert(NY)
    t = out.index.time
    return out[(t >= time(9, 30)) & (t < time(16, 0))]


def load_market_days(market: str) -> Tuple[Dict[date, pd.DataFrame], dict]:
    """Return (gby, spec) with session slicer info."""
    key = market.lower()
    if key in FUT_SPECS:
        cfg = MARKETS[key]
        print("Loading %s 1m…" % key.upper(), flush=True)
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), key)
        spec = {
            **FUT_SPECS[key],
            "kind": "fut",
            "session": "rth",
            "risk_mode": "points",
            "pip": 1.0,
        }
        return gby, spec
    if key in FX_MARKETS:
        fx = FX_MARKETS[key]
        print("Loading FX %s…" % fx.symbol, flush=True)
        gby = load_market_gby(fx)
        # interpret risk_pts as pips for FX pairs; index CFDs as points
        if fx.symbol in {"EURUSD", "GBPUSD", "AUDJPY"} or "usd" in fx.symbol.lower() and fx.tick < 0.01:
            pip = 0.0001 if fx.tick <= 0.0001 else 0.01
            if fx.symbol == "USDJPY":
                pip = 0.01
            risk_mode = "pips"
        else:
            pip = 1.0
            risk_mode = "points"
        spec = {
            "point_value": fx.point_value,
            "fee_rt": fx.fee_per_unit,
            "label": fx.key,
            "kind": "fx",
            "session": fx.clock.name,
            "clock": fx.clock,
            "risk_mode": risk_mode,
            "pip": pip,
        }
        return gby, spec
    raise SystemExit("unknown market %s" % market)


def session_1m(raw: pd.DataFrame, day: date, spec: dict) -> pd.DataFrame:
    if spec["kind"] == "fut":
        return _rth_fut(raw)
    clock = spec["clock"]
    return session_bars(raw, day, clock, dense=False).dropna(subset=["open", "high", "low", "close"])


def risk_price(risk_pts: float, spec: dict) -> float:
    if spec.get("risk_mode") == "pips":
        return float(risk_pts) * float(spec["pip"])
    return float(risk_pts)


def manage_bar(
    position: dict,
    *,
    ts: pd.Timestamp,
    h: float,
    l: float,
    c: float,
    st_px: float,
    trend: int,
    plan: Plan,
    point_value: float,
    fee_rt: float,
    is_session_end: bool,
) -> Optional[Trade]:
    side = position["side"]
    stop = float(position["stop"])
    entry = float(position["entry"])
    sign = 1.0 if side == "long" else -1.0
    if side == "long":
        position["mae_pts"] = max(float(position.get("mae_pts") or 0.0), entry - l)
        position["mfe_pts"] = max(float(position.get("mfe_pts") or 0.0), h - entry)
    else:
        position["mae_pts"] = max(float(position.get("mae_pts") or 0.0), h - entry)
        position["mfe_pts"] = max(float(position.get("mfe_pts") or 0.0), entry - l)

    def _realize(qty: float, px: float, tag: str) -> None:
        if qty <= 0:
            return
        pnl_pts = sign * (px - entry)
        usd = pnl_pts * point_value * qty - fee_rt * qty
        position["realized_usd"] = float(position.get("realized_usd") or 0.0) + usd
        legs = list(position.get("exit_legs") or [])
        legs.append("%s@%.6f x%.0f" % (tag, px, qty))
        position["exit_legs"] = legs
        position["qty_open"] = float(position["qty_open"]) - qty
        if tag.startswith("eod"):
            position["qty_eod"] = max(0.0, float(position.get("qty_eod") or 0) - qty)
        if tag.startswith("runner"):
            position["qty_runner"] = max(0.0, float(position.get("qty_runner") or 0) - qty)

    qty_open = float(position.get("qty_open") or 0)
    scaled = bool(position.get("scaled"))

    # 1) stop
    hit_stop = (side == "long" and l <= stop) or (side == "short" and h >= stop)
    if hit_stop and qty_open > 0:
        tag = "be_stop" if scaled else "risk_stop"
        _realize(qty_open, stop, tag)
        reason = ("scale_1r+" + tag) if scaled else tag
        return _fin(position, ts, stop, reason, plan, point_value)

    # 2) scale @ 1R
    if not scaled:
        tp1 = float(position["tp1"])
        hit_tp1 = (side == "long" and h >= tp1) or (side == "short" and l <= tp1)
        if hit_tp1:
            off = float(plan.off_1r)
            _realize(off, tp1, "scale_1r")
            position["scaled"] = True
            position["scale_px"] = tp1
            position["stop"] = entry
            # allocate remaining into eod / runner buckets
            rem = float(position["qty_open"])
            position["qty_eod"] = float(min(plan.eod_qty, rem))
            position["qty_runner"] = float(min(plan.runner_qty, rem - position["qty_eod"]))
            # leftover (if any) joins runners
            leftover = rem - position["qty_eod"] - position["qty_runner"]
            if leftover > 0:
                position["qty_runner"] += leftover
            # same-bar BE
            be = entry
            hit_be = (side == "long" and l <= be) or (side == "short" and h >= be)
            if hit_be and float(position["qty_open"]) > 0:
                _realize(float(position["qty_open"]), be, "be_stop")
                return _fin(position, ts, be, "scale_1r+be_stop", plan, point_value)

    scaled = bool(position.get("scaled"))
    # 3) runner target
    if scaled and float(position.get("qty_runner") or 0) > 0:
        tpr = float(position["tp_runner"])
        hit_r = (side == "long" and h >= tpr) or (side == "short" and l <= tpr)
        if hit_r:
            q = float(position["qty_runner"])
            _realize(q, tpr, "runner_%.0fr" % plan.runner_r)
            position["qty_runner"] = 0.0
            if float(position["qty_open"]) <= 0:
                return _fin(position, ts, tpr, "scale_1r+runner_%.0fr" % plan.runner_r, plan, point_value)

    # 4) ST flip
    st_exit = (side == "long" and trend == -1 and c < st_px) or (
        side == "short" and trend == 1 and c > st_px
    )
    if st_exit and float(position.get("qty_open") or 0) > 0:
        if not scaled or plan.st_flip_after_scale:
            q = float(position["qty_open"])
            _realize(q, c, "st_flip")
            reason = "scale_1r+st_flip" if scaled else "st_flip"
            return _fin(position, ts, c, reason, plan, point_value)
        # split15 after scale: ST flip only ignored; hold eod/runner buckets

    # 5) session EOD — flatten eod bucket (and all if never scaled)
    if is_session_end and float(position.get("qty_open") or 0) > 0:
        if not scaled:
            q = float(position["qty_open"])
            _realize(q, c, "eod_flat")
            return _fin(position, ts, c, "eod_flat", plan, point_value)
        q_eod = float(position.get("qty_eod") or 0)
        if q_eod > 0:
            _realize(q_eod, c, "eod")
            position["qty_eod"] = 0.0
        if float(position["qty_open"]) <= 0:
            return _fin(position, ts, c, "scale_1r+eod", plan, point_value)
        # runners remain overnight
    return None


def _fin(position, ts, exit_px, reason, plan: Plan, point_value: float) -> Trade:
    qty = float(position.get("qty") or 1)
    pnl_usd = float(position.get("realized_usd") or 0)
    return Trade(
        trade_id=int(position["trade_id"]),
        side=str(position["side"]),
        program=str(position["program"]),
        variant=plan.name,
        signal_ts=position["signal_ts"],
        entry_ts=position["entry_ts"],
        entry=float(position["entry"]),
        limit_px=float(position["limit_px"]),
        stop=float(position["stop"]),
        exit_ts=ts,
        exit=float(exit_px),
        exit_reason=reason,
        pnl_pts=round(pnl_usd / point_value if point_value else 0.0, 4),
        pnl_usd=round(pnl_usd, 2),
        structure_key=float(position["structure_key"]),
        st_at_signal=float(position["st_at_signal"]),
        mae_pts=round(float(position.get("mae_pts") or 0), 4),
        mfe_pts=round(float(position.get("mfe_pts") or 0), 4),
        risk_pts=float(position.get("risk_pts") or 0),
        qty=qty,
        scaled=bool(position.get("scaled")),
        scale_px=float(position["scale_px"]) if position.get("scaled") else float("nan"),
        runner_target=float(position.get("tp_runner") or float("nan")),
    )


def precompute_sessions(
    gby: Dict[date, pd.DataFrame],
    spec: dict,
    days: List[date],
) -> Dict[date, pd.DataFrame]:
    """Session bars with SuperTrend columns attached (computed once per market)."""
    cache: Dict[date, pd.DataFrame] = {}
    for di, day in enumerate(days, 1):
        raw = gby.get(day)
        sess = session_1m(raw, day, spec)
        if sess.empty or len(sess) < 60:
            continue
        # warm with prior up to 2 sessions for ST continuity
        warm_parts = []
        for prev in reversed(list(cache.values())[-2:]):
            warm_parts.append(prev.drop(columns=["supertrend", "supertrend_trend", "atr"], errors="ignore"))
        warm_parts.append(sess)
        tape = pd.concat(warm_parts)
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
        st = compute_supertrend(tape, atr_len=ATR_LEN, multiplier=ATR_MULT)
        day_st = st.loc[sess.index, ["supertrend", "supertrend_trend", "atr"]]
        out = sess.copy()
        out["supertrend"] = day_st["supertrend"].to_numpy()
        out["supertrend_trend"] = day_st["supertrend_trend"].to_numpy()
        out["atr"] = day_st["atr"].to_numpy()
        cache[day] = out
        if di % 500 == 0:
            print("  precompute ST %d/%d" % (di, len(days)), flush=True)
    print("Precomputed ST for %d sessions" % len(cache), flush=True)
    return cache


def run_one(
    *,
    market: str,
    plan: Plan,
    risk_pts: float,
    gby: Dict[date, pd.DataFrame],
    spec: dict,
    start: Optional[date] = None,
    end: Optional[date] = None,
    max_days: Optional[int] = None,
    session_cache: Optional[Dict[date, pd.DataFrame]] = None,
) -> pd.DataFrame:
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]
    if max_days:
        days = days[:max_days]

    rp = risk_price(risk_pts, spec)
    pv = float(spec["point_value"])
    fee = float(spec["fee_rt"])
    engine = StructureProgramEngine()
    pending = None
    position = None
    next_id = 1
    trades: List[Trade] = []
    ready_day = None

    if session_cache is None:
        session_cache = precompute_sessions(gby, spec, days)

    tag = "%s_%s_r%.0f" % (market, plan.name, risk_pts)
    print("=== %s  days=%d  risk=%.4g (price) ===" % (tag, len(days), rp), flush=True)

    last_sess = None
    for di, day in enumerate(days, 1):
        sess = session_cache.get(day)
        if sess is None or sess.empty:
            continue
        bars15 = to_15m(sess.drop(columns=["supertrend", "supertrend_trend", "atr"], errors="ignore"))
        engine.ingest_day_15m(bars15)
        if ready_day is None and engine.ready:
            ready_day = day
            print("  lists full %s program=%s" % (day, engine.program), flush=True)

        st_df = sess
        day_end_i = len(st_df) - 1
        highs = st_df["high"].to_numpy(dtype=float)
        lows = st_df["low"].to_numpy(dtype=float)
        closes = st_df["close"].to_numpy(dtype=float)
        sts = st_df["supertrend"].to_numpy(dtype=float)
        trends = st_df["supertrend_trend"].to_numpy(dtype=float)
        idx = st_df.index
        for i in range(len(st_df)):
            ts = idx[i]
            h, l, c = highs[i], lows[i], closes[i]
            st_px = sts[i]
            trend = int(trends[i]) if not np.isnan(trends[i]) else 0
            if np.isnan(st_px):
                continue
            st_px = float(st_px)
            is_end = i == day_end_i

            if position is not None:
                closed = manage_bar(
                    position,
                    ts=ts,
                    h=h,
                    l=l,
                    c=c,
                    st_px=st_px,
                    trend=trend,
                    plan=plan,
                    point_value=pv,
                    fee_rt=fee,
                    is_session_end=is_end,
                )
                if closed is not None:
                    trades.append(closed)
                    position = None
                    pending = None
                    continue

            if position is None and pending is not None:
                side = pending["side"]
                lim = float(pending["limit_px"])
                stop_p = float(pending["stop"])
                blown = (side == "long" and l <= stop_p) or (side == "short" and h >= stop_p)
                filled = (side == "long" and l <= lim) or (side == "short" and h >= lim)
                cancel_prog = engine.program is not None and (
                    (side == "long" and engine.program != "buy")
                    or (side == "short" and engine.program != "sell")
                )
                if blown or cancel_prog:
                    pending = None
                elif filled:
                    sign = 1.0 if side == "long" else -1.0
                    position = {
                        **pending,
                        "entry_ts": ts,
                        "entry": lim,
                        "trade_id": next_id,
                        "mae_pts": 0.0,
                        "mfe_pts": 0.0,
                        "qty": float(plan.entry_qty),
                        "qty_open": float(plan.entry_qty),
                        "qty_eod": 0.0,
                        "qty_runner": 0.0,
                        "scaled": False,
                        "realized_usd": 0.0,
                        "scale_px": float("nan"),
                        "tp1": lim + sign * rp,
                        "tp_runner": lim + sign * plan.runner_r * rp,
                        "exit_legs": [],
                    }
                    next_id += 1
                    pending = None

            if position is None and pending is not None and is_end:
                pending["rth_closes"] = int(pending.get("rth_closes") or 0) + 1
                if pending["rth_closes"] >= STRUCTURE_SL_PENDING_MAX_CLOSES:
                    pending = None

            if position is None and pending is None and engine.ready and engine.program is not None:
                if i < 1:
                    continue
                prev_trend = int(trends[i - 1]) if not np.isnan(trends[i - 1]) else 0
                prev_st = sts[i - 1]
                if np.isnan(prev_st):
                    continue
                prev_st = float(prev_st)
                prog = engine.program
                if prog == "buy" and prev_trend == -1 and trend == 1 and c > prev_st:
                    sk = engine.latest_key("bull")
                    if sk is not None and sk < prev_st:
                        pending = {
                            "side": "long",
                            "program": prog,
                            "signal_ts": ts,
                            "limit_px": sk,
                            "stop": sk - rp,
                            "structure_key": sk,
                            "st_at_signal": prev_st,
                            "risk_pts": risk_pts,
                            "rth_closes": 0,
                        }
                elif prog == "sell" and prev_trend == 1 and trend == -1 and c < prev_st:
                    sk = engine.latest_key("bear")
                    if sk is not None and sk > prev_st:
                        pending = {
                            "side": "short",
                            "program": prog,
                            "signal_ts": ts,
                            "limit_px": sk,
                            "stop": sk + rp,
                            "structure_key": sk,
                            "st_at_signal": prev_st,
                            "risk_pts": risk_pts,
                            "rth_closes": 0,
                        }
        last_sess = sess
        if di % 500 == 0:
            print("  %d/%d trades=%d program=%s" % (di, len(days), len(trades), engine.program), flush=True)

    if position is not None and last_sess is not None and not last_sess.empty:
        ts = last_sess.index[-1]
        c = float(last_sess.iloc[-1]["close"])
        sign = 1.0 if position["side"] == "long" else -1.0
        q = float(position["qty_open"])
        pnl = sign * (c - float(position["entry"])) * pv * q - fee * q
        position["realized_usd"] = float(position.get("realized_usd") or 0) + pnl
        trades.append(_fin(position, ts, c, "force_flat", plan, pv))

    out_dir = OUT_ROOT / market / ("%s_r%.0f" % (plan.name, risk_pts))
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in trades])
    if not df.empty:
        df.to_csv(out_dir / "trades.csv", index=False)
        _write_mae_profile(df, out_dir)
    meta = {
        "market": market,
        "plan": plan.name,
        "risk_pts": risk_pts,
        "risk_price": rp,
        "point_value": pv,
        "ready_day": str(ready_day),
        "n_days": len(days),
        "n_trades": len(df),
        "final_program": engine.program,
        "label": spec.get("label", market),
    }
    pd.Series(meta).to_csv(out_dir / "meta.csv")
    _write_run_summary(df, meta, out_dir, plan)
    print("  → %d trades net=$%.0f → %s" % (len(df), 0 if df.empty else df.pnl_usd.sum(), out_dir), flush=True)
    return df


def _write_run_summary(df: pd.DataFrame, meta: dict, out_dir: Path, plan: Plan) -> None:
    lines = [
        "# %s / %s / risk %.0f (%s)" % (meta["market"], plan.name, float(meta["risk_pts"]), meta.get("label", "")),
        "",
        "Entry @ structure after 1m ST break; stop = structure ± risk. "
        "Plan **%s**: %dct, %d@1R→BE, %d@EOD, %d runners @%.0fR (ST-flip after scale=%s)."
        % (
            plan.name,
            plan.entry_qty,
            plan.off_1r,
            plan.eod_qty,
            plan.runner_qty,
            plan.runner_r,
            plan.st_flip_after_scale,
        ),
        "",
        "## Meta",
        "",
    ]
    for k, v in meta.items():
        lines.append("- **%s:** %s" % (k, v))
    lines.append("")
    if df is None or df.empty:
        lines.append("No trades.")
        (out_dir / "SUMMARY.md").write_text("\n".join(lines))
        return
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    pf = wins.pnl_usd.sum() / abs(losses.pnl_usd.sum()) if len(losses) and losses.pnl_usd.sum() else float("inf")
    lines += [
        "## Results",
        "",
        "| metric | value |",
        "|---|---|",
        "| trades | %d |" % len(df),
        "| net $ | %.0f |" % df.pnl_usd.sum(),
        "| win%% | %.1f |" % (100 * (df.pnl_usd > 0).mean()),
        "| PF | %.3f |" % pf,
        "| avg $/trade | %.1f |" % df.pnl_usd.mean(),
        "| MAE med | %.2f |" % df.mae_pts.median(),
        "| scaled %% | %.0f |" % (100 * df.scaled.mean() if "scaled" in df.columns else 0),
        "",
        "### By exit reason",
        "",
        _md_agg(df.groupby("exit_reason").pnl_usd.agg(["count", "sum", "mean"])),
        "",
        "### By year",
        "",
        _md_agg(
            df.assign(year=pd.to_datetime(df.entry_ts, utc=True).dt.year)
            .groupby("year")
            .pnl_usd.agg(["count", "sum", "mean"])
        ),
        "",
    ]
    (out_dir / "SUMMARY.md").write_text("\n".join(lines))


def write_sweep_table(rows: List[dict], path: Path, title: str) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows).sort_values(["plan", "risk_pts", "market"])
    df.to_csv(path.with_suffix(".csv"), index=False)
    lines = ["# " + title, "", _md_agg(df.set_index(df.columns[0])), ""]
    # pick best by net then PF
    best = df.sort_values(["net_usd", "profit_factor"], ascending=False).iloc[0]
    lines.append(
        "**Best row:** market=%s plan=%s risk=%.0f net=$%.0f PF=%.3f WR=%.1f%% (n=%d)"
        % (
            best.market,
            best.plan,
            best.risk_pts,
            best.net_usd,
            best.profit_factor,
            best.win_pct,
            best.trades,
        )
    )
    path.write_text("\n".join(lines))
    print("Sweep table → %s" % path, flush=True)


def row_from_df(market: str, plan: str, risk: float, df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "market": market,
            "plan": plan,
            "risk_pts": risk,
            "trades": 0,
            "net_usd": 0.0,
            "win_pct": 0.0,
            "profit_factor": 0.0,
            "avg_usd": 0.0,
            "mae_med": 0.0,
            "scaled_pct": 0.0,
        }
    wins = df[df.pnl_usd > 0]
    losses = df[df.pnl_usd <= 0]
    pf = wins.pnl_usd.sum() / abs(losses.pnl_usd.sum()) if len(losses) and losses.pnl_usd.sum() else float("inf")
    return {
        "market": market,
        "plan": plan,
        "risk_pts": risk,
        "trades": len(df),
        "net_usd": round(float(df.pnl_usd.sum()), 2),
        "win_pct": round(100 * float((df.pnl_usd > 0).mean()), 1),
        "profit_factor": round(float(pf), 3) if pf != float("inf") else 999.0,
        "avg_usd": round(float(df.pnl_usd.mean()), 1),
        "mae_med": round(float(df.mae_pts.median()), 2),
        "scaled_pct": round(100 * float(df.scaled.mean()), 1) if "scaled" in df.columns else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="+", default=["nq"])
    ap.add_argument("--plan", choices=list(PLANS), default="scale4")
    ap.add_argument("--plans", default=None, help="comma list, overrides --plan")
    ap.add_argument("--risks", default="8,10,12,16,20")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-days", type=int, default=None)
    args = ap.parse_args()

    risks = [float(x) for x in args.risks.split(",") if x.strip()]
    plans = [PLANS[p.strip()] for p in (args.plans.split(",") if args.plans else [args.plan])]
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    all_rows: List[dict] = []
    for market in args.markets:
        gby, spec = load_market_days(market)
        days = sorted(gby)
        if start:
            days = [d for d in days if d >= start]
        if end:
            days = [d for d in days if d <= end]
        if args.max_days:
            days = days[: args.max_days]
        cache = precompute_sessions(gby, spec, days)
        for plan in plans:
            for risk in risks:
                out_dir = OUT_ROOT / market / ("%s_r%.0f" % (plan.name, risk))
                reuse = out_dir / "trades.csv"
                legacy = OUT_ROOT / "structure_sl_scale" / "trades.csv"
                if reuse.exists():
                    df = pd.read_csv(reuse)
                    print("Skip existing %s (%d trades)" % (out_dir, len(df)), flush=True)
                elif (
                    market == "nq"
                    and plan.name == "scale4"
                    and risk == 8.0
                    and legacy.exists()
                ):
                    prev = pd.read_csv(legacy)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    prev.to_csv(reuse, index=False)
                    df = prev
                    _write_run_summary(
                        df,
                        {
                            "market": "nq",
                            "plan": "scale4",
                            "risk_pts": 8.0,
                            "risk_price": 8.0,
                            "point_value": 20.0,
                            "n_trades": len(df),
                            "label": "NQ",
                        },
                        out_dir,
                        plan,
                    )
                    print("Reusing prior structure_sl_scale as nq/scale4_r8", flush=True)
                else:
                    df = run_one(
                        market=market,
                        plan=plan,
                        risk_pts=risk,
                        gby=gby,
                        spec=spec,
                        start=start,
                        end=end,
                        max_days=args.max_days,
                        session_cache=cache,
                    )
                all_rows.append(row_from_df(market, plan.name, risk, df))

    sweep_path = OUT_ROOT / "SWEEP.md"
    write_sweep_table(all_rows, sweep_path, "Structure-program ST sweep")


if __name__ == "__main__":
    main()
