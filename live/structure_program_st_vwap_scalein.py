"""Structure-zone VWAP split entry (analytic).

When the structure program is active, scale into the trade with spaced VWAP
limits *inside* the latest structure:

  Bull / buy program: structure = [LL, HH]; VWAP buy slices; SL at LL (bottom)
  Bear / sell program: structure = [LL, HH]; VWAP sell slices; SL at HH (top)

Rules:
  - Full size 15ct in 5×3 slices (only if market allows fills)
  - At most one slice per completed 15m bar (buys spaced out)
  - Limit at session RTH VWAP; fill only while price is inside the structure
  - If stopped at structure extreme: wait for a *15m close* back inside the
    structure before arming buys again
  - Exit ladder from average entry: 5@+25 → ±12 tight (or BE if full), then
    5@+50 / 5@+200; favourable ST → BE (same family shape)
  - Flatten at RTH 15:59 (structure is intraday; avoids multi-day BE holds on RTH tape)

Usage:
  python -m live.structure_program_st_vwap_scalein --start 2020-01-01
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    FEE_PER_CONTRACT_RT,
    POINT_VALUE,
    RUN_TP2_PTS,
    RUN_TP3_PTS,
    Structure,
    StructureProgramEngine,
    TOUCH_ALIGN_TIGHT_SL,
    TOUCH_ALIGN_TP1_PTS,
    rth_slice,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st" / "vwap_scalein"
NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)

N_SLICES = 5
SLICE_QTY = 3
FULL_QTY = N_SLICES * SLICE_QTY  # 15


@dataclass
class Campaign:
    trade_id: int
    side: str
    program: str
    bottom: float
    top: float
    structure_key: float
    signal_ts: pd.Timestamp
    entry_ts: Optional[pd.Timestamp] = None
    avg_entry: float = 0.0
    qty: float = 0.0
    qty_open: float = 0.0
    stop: float = 0.0
    slices: int = 0
    last_slice_bucket: Optional[pd.Timestamp] = None
    scaled: bool = False
    scaled2: bool = False
    st_be_armed: bool = False
    realized_usd: float = 0.0
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    hit_25: bool = False
    hit_100: bool = False
    hit_200: bool = False
    exit_legs: List[str] = field(default_factory=list)
    pending_limit: Optional[float] = None


@dataclass
class TradeRow:
    trade_id: int
    side: str
    program: str
    variant: str
    signal_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    limit_px: float
    stop: float
    exit_ts: pd.Timestamp
    exit: float
    exit_reason: str
    pnl_pts: float
    pnl_usd: float
    structure_key: float
    st_at_signal: float
    mae_pts: float
    mfe_pts: float
    risk_pts: float
    qty: float
    slices: int
    scaled: bool
    hit_25: bool
    hit_100: bool
    hit_200: bool
    st_be_armed: bool


def _bucket_15(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.floor("15min")


def _structure_bounds(st: Structure) -> Tuple[float, float, float]:
    """Return bottom, top, key."""
    if st.kind == "bull":
        bottom, top, key = float(st.key), float(st.p4), float(st.key)
    else:
        bottom, top, key = float(st.p4), float(st.key), float(st.key)
    if bottom > top:
        bottom, top = top, bottom
    return bottom, top, key


def _in_structure(px: float, bottom: float, top: float) -> bool:
    return bottom <= px <= top


def _finalize(camp: Campaign, ts: pd.Timestamp, exit_px: float, reason: str) -> TradeRow:
    qty = float(camp.qty) or 1.0
    pnl = float(camp.realized_usd)
    return TradeRow(
        trade_id=camp.trade_id,
        side=camp.side,
        program=camp.program,
        variant="vwap_scalein",
        signal_ts=camp.signal_ts,
        entry_ts=camp.entry_ts or camp.signal_ts,
        entry=float(camp.avg_entry),
        limit_px=float(camp.structure_key),
        stop=float(camp.stop),
        exit_ts=ts,
        exit=float(exit_px),
        exit_reason=reason,
        pnl_pts=round(pnl / POINT_VALUE, 4),
        pnl_usd=round(pnl, 2),
        structure_key=float(camp.structure_key),
        st_at_signal=float(camp.structure_key),
        mae_pts=round(float(camp.mae_pts), 4),
        mfe_pts=round(float(camp.mfe_pts), 4),
        risk_pts=round(abs(float(camp.avg_entry) - float(camp.stop)), 4) if camp.avg_entry else 0.0,
        qty=qty,
        slices=int(camp.slices),
        scaled=bool(camp.scaled),
        hit_25=bool(camp.hit_25),
        hit_100=bool(camp.hit_100),
        hit_200=bool(camp.hit_200),
        st_be_armed=bool(camp.st_be_armed),
    )


def _realize(camp: Campaign, qty: float, px: float, tag: str) -> None:
    sign = 1.0 if camp.side == "long" else -1.0
    pnl_pts = sign * (px - float(camp.avg_entry))
    usd = pnl_pts * POINT_VALUE * qty - FEE_PER_CONTRACT_RT * qty
    camp.realized_usd += usd
    camp.exit_legs.append("%s@%.2f x%.0f" % (tag, px, qty))
    camp.qty_open = float(camp.qty_open) - qty


def _compose_reason(camp: Campaign, final: str) -> str:
    tags = [str(x).split("@", 1)[0] for x in camp.exit_legs]
    out: List[str] = []
    for t in tags:
        if not out or out[-1] != t:
            out.append(t)
    if not out or out[-1] != final:
        out.append(final)
    return "+".join(out)


def run_study(
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    max_days: Optional[int] = None,
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
    if max_days:
        days = days[:max_days]

    engine = StructureProgramEngine()
    recent: List[pd.DataFrame] = []
    camp: Optional[Campaign] = None
    wait_reclaim = False
    wait_bounds: Optional[Tuple[float, float]] = None
    next_id = 1
    trades: List[TradeRow] = []
    last_closed_15: Optional[pd.Timestamp] = None

    print("Running vwap_scalein over %d days…" % len(days), flush=True)
    for di, day in enumerate(days, 1):
        rth = rth_slice(gby.get(day))
        if rth.empty or len(rth) < 60:
            continue
        bars_15 = to_15m(rth)
        engine.ingest_day_15m(bars_15)

        tape = pd.concat(recent + [rth]) if recent else rth
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
        st_df = compute_supertrend(tape, atr_len=ATR_LEN, multiplier=ATR_MULT)

        # session VWAP on day RTH
        vwap_num = 0.0
        vwap_den = 0.0
        last_closed_15 = _bucket_15(rth.index[0])

        for i, (ts, row) in enumerate(rth.iterrows()):
            o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
            vol = float(row["volume"]) if "volume" in row.index and float(row.get("volume") or 0) > 0 else 1.0
            tp = (h + l + c) / 3.0
            vwap_num += tp * vol
            vwap_den += vol
            vwap = vwap_num / vwap_den if vwap_den > 0 else c
            bucket = _bucket_15(ts)

            # ST at this ts
            if ts in st_df.index:
                st_row = st_df.loc[ts]
                if isinstance(st_row, pd.DataFrame):
                    st_row = st_row.iloc[-1]
                st_px = st_row.get("supertrend")
                trend = int(st_row["supertrend_trend"]) if not pd.isna(st_row.get("supertrend_trend")) else 0
                st_px = float(st_px) if not pd.isna(st_px) else None
            else:
                st_px, trend = None, 0

            # detect newly completed 15m close (previous bucket ended)
            if last_closed_15 is None:
                last_closed_15 = bucket
            completed_close = None
            if bucket != last_closed_15:
                prior = rth[(rth.index >= last_closed_15) & (rth.index < bucket)]
                if not prior.empty:
                    completed_close = float(prior.iloc[-1]["close"])
                last_closed_15 = bucket

            prog = engine.program
            ready = engine.ready and prog in {"buy", "sell"}

            # reclaim gate after stop-out: 15m close inside *current* structure
            if wait_reclaim and completed_close is not None and ready:
                st_obj = engine.latest("bull" if prog == "buy" else "bear")
                if st_obj is not None:
                    b, t_, _k = _structure_bounds(st_obj)
                    if _in_structure(completed_close, b, t_):
                        wait_reclaim = False
                        wait_bounds = None

            # --- manage open campaign ---
            if camp is not None and camp.qty_open > 0:
                entry = float(camp.avg_entry)
                sign = 1.0 if camp.side == "long" else -1.0
                if camp.side == "long":
                    camp.mae_pts = max(camp.mae_pts, entry - l)
                    camp.mfe_pts = max(camp.mfe_pts, h - entry)
                else:
                    camp.mae_pts = max(camp.mae_pts, h - entry)
                    camp.mfe_pts = max(camp.mfe_pts, entry - l)
                if camp.mfe_pts >= 25:
                    camp.hit_25 = True
                if camp.mfe_pts >= 100:
                    camp.hit_100 = True
                if camp.mfe_pts >= 200:
                    camp.hit_200 = True

                # structure stop
                hit_stop = (camp.side == "long" and l <= camp.stop) or (
                    camp.side == "short" and h >= camp.stop
                )
                if hit_stop:
                    tag = "structure_stop"
                    _realize(camp, float(camp.qty_open), float(camp.stop), tag)
                    trades.append(_finalize(camp, ts, float(camp.stop), _compose_reason(camp, tag)))
                    wait_reclaim = True
                    wait_bounds = (camp.bottom, camp.top)
                    camp = None
                    continue

                # program flip against
                if prog is not None and (
                    (camp.side == "long" and prog != "buy")
                    or (camp.side == "short" and prog != "sell")
                ):
                    _realize(camp, float(camp.qty_open), c, "program_flip")
                    trades.append(_finalize(camp, ts, c, _compose_reason(camp, "program_flip")))
                    camp = None
                    continue

                # scale ladder from avg
                if not camp.scaled and camp.qty_open > 0:
                    tp1 = entry + sign * TOUCH_ALIGN_TP1_PTS
                    hit = (camp.side == "long" and h >= tp1) or (camp.side == "short" and l <= tp1)
                    if hit:
                        q = min(5.0, float(camp.qty_open))
                        _realize(camp, q, tp1, "scale_25")
                        camp.scaled = True
                        tight = TOUCH_ALIGN_TIGHT_SL
                        camp.stop = entry - tight if camp.side == "long" else entry + tight
                        if camp.qty_open > 0:
                            hit_t = (camp.side == "long" and l <= camp.stop) or (
                                camp.side == "short" and h >= camp.stop
                            )
                            if hit_t:
                                _realize(camp, float(camp.qty_open), float(camp.stop), "tight_stop")
                                trades.append(
                                    _finalize(camp, ts, float(camp.stop), _compose_reason(camp, "tight_stop"))
                                )
                                camp = None
                                continue
                if camp is not None and camp.scaled and not camp.scaled2 and camp.qty_open > 0:
                    tp2 = entry + sign * RUN_TP2_PTS
                    hit = (camp.side == "long" and h >= tp2) or (camp.side == "short" and l <= tp2)
                    if hit:
                        q = min(5.0, float(camp.qty_open))
                        _realize(camp, q, tp2, "scale_50")
                        camp.scaled2 = True
                if camp is not None and camp.scaled2 and camp.qty_open > 0:
                    tpr = entry + sign * RUN_TP3_PTS
                    hit = (camp.side == "long" and h >= tpr) or (camp.side == "short" and l <= tpr)
                    if hit:
                        _realize(camp, float(camp.qty_open), tpr, "runner_200")
                        trades.append(_finalize(camp, ts, tpr, _compose_reason(camp, "runner_200")))
                        camp = None
                        continue

                # ST flip (match plugin fav_be: arm BE once; adverse/flat → flatten)
                if camp is not None and st_px is not None and camp.qty_open > 0:
                    st_exit = (camp.side == "long" and trend == -1 and c < st_px) or (
                        camp.side == "short" and trend == 1 and c > st_px
                    )
                    if st_exit:
                        fav = (camp.side == "long" and c > entry) or (
                            camp.side == "short" and c < entry
                        )
                        adverse = (camp.side == "long" and c < entry) or (
                            camp.side == "short" and c > entry
                        )
                        if fav and not camp.st_be_armed:
                            camp.stop = entry
                            camp.st_be_armed = True
                        elif adverse or not fav:
                            _realize(camp, float(camp.qty_open), c, "st_flip")
                            trades.append(_finalize(camp, ts, c, _compose_reason(camp, "st_flip")))
                            camp = None
                            continue

                # RTH EOD flatten (structure is intraday; avoids multi-day BE holds)
                if camp is not None and camp.qty_open > 0 and ts.time() >= time(15, 59):
                    _realize(camp, float(camp.qty_open), c, "eod")
                    trades.append(_finalize(camp, ts, c, _compose_reason(camp, "eod")))
                    camp = None
                    continue

            if camp is None and wait_reclaim:
                continue
            if not ready:
                continue
            if ts.time() >= time(15, 59):
                continue

            st_obj = engine.latest("bull" if prog == "buy" else "bear")
            if st_obj is None:
                continue
            bottom, top, key = _structure_bounds(st_obj)
            side = "long" if prog == "buy" else "short"
            stop0 = bottom if side == "long" else top

            # Drop empty wrong-side shell; only create campaign on first fill
            if camp is not None and camp.qty_open <= 0:
                camp = None
            if camp is not None and camp.side != side:
                if camp.qty_open <= 0:
                    camp = None
                else:
                    continue

            # update bounds if structure refreshes same side (keep stop at extreme)
            if camp is not None and camp.side == side:
                camp.bottom, camp.top, camp.structure_key = bottom, top, key
                if not camp.scaled and not camp.st_be_armed:
                    camp.stop = stop0

            slices_done = camp.slices if camp is not None else 0
            qty_done = camp.qty if camp is not None else 0.0
            if slices_done >= N_SLICES or qty_done >= FULL_QTY:
                continue
            last_b = camp.last_slice_bucket if camp is not None else None
            if last_b is not None and last_b == bucket:
                continue

            camp_bottom = camp.bottom if camp is not None else bottom
            camp_top = camp.top if camp is not None else top
            camp_stop = camp.stop if camp is not None else stop0
            camp_side = camp.side if camp is not None else side

            if not _in_structure(c, camp_bottom, camp_top) and not _in_structure(vwap, camp_bottom, camp_top):
                continue

            # VWAP must sit inside structure with usable room to the structure stop
            if not _in_structure(vwap, camp_bottom, camp_top):
                continue
            min_risk = float(TOUCH_ALIGN_TIGHT_SL)
            if camp_side == "long" and (vwap - camp_stop) < min_risk:
                continue
            if camp_side == "short" and (camp_stop - vwap) < min_risk:
                continue

            filled = False
            fill_px = vwap
            if camp_side == "long" and l <= vwap:
                fill_px = min(vwap, o) if o < vwap else vwap
                filled = True
            elif camp_side == "short" and h >= vwap:
                fill_px = max(vwap, o) if o > vwap else vwap
                filled = True

            if not filled:
                continue

            # reject fill if it would be through the stop / too tight
            if camp_side == "long" and (fill_px - camp_stop) < min_risk:
                continue
            if camp_side == "short" and (camp_stop - fill_px) < min_risk:
                continue

            if camp is None:
                if not _in_structure(c, bottom, top) and not _in_structure(vwap, bottom, top):
                    continue
                camp = Campaign(
                    trade_id=next_id,
                    side=side,
                    program=prog,
                    bottom=bottom,
                    top=top,
                    structure_key=key,
                    signal_ts=ts,
                    stop=stop0,
                )
                next_id += 1
                camp_stop = stop0

            q = float(SLICE_QTY)
            if camp.qty <= 0:
                camp.avg_entry = fill_px
                camp.entry_ts = ts
            else:
                camp.avg_entry = (camp.avg_entry * camp.qty + fill_px * q) / (camp.qty + q)
            camp.qty += q
            camp.qty_open += q
            camp.slices += 1
            camp.last_slice_bucket = bucket

        # safety: flatten any residual open qty at last RTH print
        if camp is not None and camp.qty_open > 0:
            last_ts = rth.index[-1]
            last_c = float(rth.iloc[-1]["close"])
            _realize(camp, float(camp.qty_open), last_c, "eod")
            trades.append(_finalize(camp, last_ts, last_c, _compose_reason(camp, "eod")))
            camp = None
        elif camp is not None and camp.qty_open <= 0:
            camp = None

        recent.append(rth)
        recent = recent[-3:]
        if di % 250 == 0:
            print(
                "  %d/%d days | trades %d | program=%s | open_slices=%s"
                % (
                    di,
                    len(days),
                    len(trades),
                    engine.program,
                    camp.slices if camp else 0,
                ),
                flush=True,
            )

    # flatten any residual at last close
    if camp is not None and camp.qty_open > 0:
        last_ts = rth.index[-1]
        last_c = float(rth.iloc[-1]["close"])
        _realize(camp, float(camp.qty_open), last_c, "eod_residual")
        trades.append(_finalize(camp, last_ts, last_c, _compose_reason(camp, "eod_residual")))

    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(t) for t in trades])
    if not df.empty:
        df.to_csv(OUT / "trades.csv", index=False)
    _write_summary(df)
    print("Wrote %d trades → %s" % (len(df), OUT), flush=True)
    return df


def _write_summary(df: pd.DataFrame) -> None:
    lines = [
        "# Structure VWAP scale-in (NQ RTH)",
        "",
        "Split VWAP entries inside the active structure; SL at structure bottom/top; "
        "re-arm only after a 15m close back inside after a stop-out. "
        "**%d×%dct** slices (full %d only if filled). Ladder from avg: 5@+%.0f→±%.0f, "
        "5@+%.0f, 5@+%.0f; fav ST→BE."
        % (N_SLICES, SLICE_QTY, FULL_QTY, TOUCH_ALIGN_TP1_PTS, TOUCH_ALIGN_TIGHT_SL, RUN_TP2_PTS, RUN_TP3_PTS),
        "",
    ]
    if df is None or df.empty:
        lines.append("No trades.")
        (OUT / "SUMMARY.md").write_text("\n".join(lines))
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
        "| win%% | %.1f |" % (100.0 * (df.pnl_usd > 0).mean()),
        "| PF | %.3f |" % pf,
        "| avg $/trade | %.1f |" % df.pnl_usd.mean(),
        "| avg slices | %.2f |" % df.slices.mean(),
        "| pct full size (%d) | %.1f |" % (FULL_QTY, 100.0 * (df.qty >= FULL_QTY).mean()),
        "| long / short | %d / %d |"
        % (int((df.side == "long").sum()), int((df.side == "short").sum())),
        "",
        "### By exit reason",
        "",
    ]
    g = df.groupby("exit_reason")["pnl_usd"].agg(["count", "sum", "mean"])
    try:
        lines.append(g.to_markdown())
    except Exception:
        lines.append(g.to_string())
    lines += ["", "### By year", ""]
    y = df.copy()
    y["year"] = pd.to_datetime(y["entry_ts"]).dt.year
    yg = y.groupby("year")["pnl_usd"].agg(["count", "sum", "mean"])
    try:
        lines.append(yg.to_markdown())
    except Exception:
        lines.append(yg.to_string())
    (OUT / "SUMMARY.md").write_text("\n".join(lines))
    meta = {
        "variant": "vwap_scalein",
        "n_trades": len(df),
        "net_usd": float(df.pnl_usd.sum()),
        "profit_factor": float(pf) if np.isfinite(pf) else None,
        "win_rate": float((df.pnl_usd > 0).mean()),
        "avg_slices": float(df.slices.mean()),
        "pct_full_size": float((df.qty >= FULL_QTY).mean()),
    }
    pd.Series(meta).to_csv(OUT / "meta.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-days", type=int, default=0)
    args = ap.parse_args()
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    run_study(start=start, end=end, max_days=args.max_days or None)


if __name__ == "__main__":
    main()
