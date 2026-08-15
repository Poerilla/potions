"""Post-process ST+PMC long-runner target length sweep (k× TP1).

Uses existing ``*_runners_2r_indef`` unit tapes (uncensored long leg). Freezes
TP1 + 2R legs; resimulates the long runner on the 1m path for
k ∈ {2,3,4,5,6,7,8,9,10,12,15} ∪ {indef}.

Validates k=10 against existing ``*_runners_2r_10r`` audits when present.
JPY pairs converted to USD: points × 100000 / rate − fee.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "st_pmc_runner_length_sweep"
FEE_USD = 1.50
JPY_PV = 100000.0
K_GRID: Tuple[Optional[float], ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, None)
TOL_FRAC = 0.15  # classify target legs within 15% of nominal pts


@dataclass(frozen=True)
class MarketSpec:
    key: str
    instrument: str
    stop_pts: float
    tp_pts: float
    tick: float
    is_jpy: bool
    one_m_path: Path
    indef_unit_fills: Path
    indef_state_fills: Path
    ref_10r_unit_fills: Optional[Path]
    fair_3r_net_usd: float
    fair_3r_stress_usd: float
    fair_3r_ns: float


@dataclass
class Leg:
    trade_id: str
    role: str  # tp1 | runner_2r | long
    direction: str
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    exit_reason: str
    points: float
    be_after_ts: str = ""


@dataclass
class SimExit:
    exit_ts: str
    exit_price: float
    exit_reason: str
    points: float


def _market_specs() -> List[MarketSpec]:
    us30_hub = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
    fx_hub = REPO / "live" / "state" / "fx_index_metals_st_pmc_runner_variants"

    def fx(key: str, inst: str, stop: float, tp: float, tick: float, is_jpy: bool, fair: Tuple[float, float, float]) -> MarketSpec:
        sid_indef = "%s_hourly_st_pmc_sl50_tp150_runners_2r_indef" % key
        sid_10r = "%s_hourly_st_pmc_sl50_tp150_runners_2r_10r" % key
        uf10 = fx_hub / key / "audits" / sid_10r / sid_10r / "unit_fills.csv"
        return MarketSpec(
            key=key,
            instrument=inst,
            stop_pts=stop,
            tp_pts=tp,
            tick=tick,
            is_jpy=is_jpy,
            one_m_path=REPO / "fx" / ("%s_1m.csv" % key),
            indef_unit_fills=fx_hub / key / "audits" / sid_indef / sid_indef / "unit_fills.csv",
            indef_state_fills=fx_hub / key / "states" / sid_indef / "fills.csv",
            ref_10r_unit_fills=uf10 if uf10.exists() else None,
            fair_3r_net_usd=fair[0],
            fair_3r_stress_usd=fair[1],
            fair_3r_ns=fair[2],
        )

    us30_indef = "us30_hourly_st_pmc_sl50_tp150_runners_2r_indef"
    us30_10r = "us30_hourly_st_pmc_sl50_tp150_runners_2r_10r"
    # Prefer lot-correct unit tapes (trade_id match); legacy audits can scramble legs.
    uf_indef = (
        us30_hub
        / "audits_lot_correct"
        / us30_indef
        / ("%s_lot_correct" % us30_indef)
        / "unit_fills.csv"
    )
    if not uf_indef.exists():
        uf_indef = us30_hub / "audits" / us30_indef / us30_indef / "unit_fills.csv"
    uf10 = (
        us30_hub
        / "audits_lot_correct"
        / us30_10r
        / ("%s_lot_correct" % us30_10r)
        / "unit_fills.csv"
    )
    if not uf10.exists():
        uf10 = us30_hub / "audits" / us30_10r / us30_10r / "unit_fills.csv"
    specs = [
        MarketSpec(
            key="us30",
            instrument="US30",
            stop_pts=50.0,
            tp_pts=150.0,
            tick=0.1,
            is_jpy=False,
            one_m_path=REPO / "fx" / "us30_1m.csv",
            indef_unit_fills=uf_indef,
            indef_state_fills=us30_hub / "states" / us30_indef / "fills.csv",
            ref_10r_unit_fills=uf10 if uf10.exists() else None,
            fair_3r_net_usd=19027.57,
            fair_3r_stress_usd=-647.43,
            fair_3r_ns=29.389,
        ),
        fx("nas100", "NAS100", 50.0, 150.0, 0.1, False, (15219.0, -778.0, 19.56)),
        fx("eurusd", "EURUSD", 0.0050, 0.0150, 0.00001, False, (64448.75, -21432.16, 3.01)),
        fx("gbpusd", "GBPUSD", 0.0050, 0.0150, 0.00001, False, (108058.0, -13310.0, 8.12)),
        fx("usdjpy", "USDJPY", 0.50, 1.50, 0.001, True, (30407.0, -19540.0, 1.56)),
    ]
    return specs


def _read_units(path: Path) -> List[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _classify_legs(units: Sequence[dict], tp: float, stop: float) -> List[Leg]:
    """Classify TP1 / 2R / long by outcome points (entry_reason labels are unreliable)."""
    tol_tp = max(abs(tp) * TOL_FRAC, abs(tp) * 0.05)
    tol_stop = max(abs(stop) * 0.5, abs(stop) * 0.25)  # allow slip
    parsed = []
    for u in units:
        parsed.append(
            {
                "trade_id": u["trade_id"],
                "direction": u["direction"],
                "entry_ts": u["entry_ts"],
                "entry_price": float(u["entry_price"]),
                "exit_ts": u["exit_ts"],
                "exit_price": float(u["exit_price"]),
                "exit_reason": u.get("exit_reason") or "",
                "points": float(u["points"]),
                "be_after_ts": u.get("be_after_ts") or "",
            }
        )

    def as_leg(role: str, u: dict, be_ts: str) -> Leg:
        return Leg(
            trade_id=u["trade_id"],
            role=role,
            direction=u["direction"],
            entry_ts=u["entry_ts"],
            entry_price=u["entry_price"],
            exit_ts=u["exit_ts"],
            exit_price=u["exit_price"],
            exit_reason=u["exit_reason"],
            points=u["points"],
            be_after_ts=be_ts or u["be_after_ts"],
        )

    if len(parsed) != 3:
        parsed = sorted(parsed, key=lambda x: x["exit_ts"])
        if len(parsed) == 1:
            return [as_leg("long", parsed[0], "")]
        if len(parsed) == 2:
            return [as_leg("tp1", parsed[0], ""), as_leg("long", parsed[1], "")]
        return []

    idxs = [0, 1, 2]

    def closest(cands: Sequence[int], target: float) -> Tuple[Optional[int], float]:
        best_i, best_err = None, 1e18
        for i in cands:
            err = abs(parsed[i]["points"] - target)
            if err < best_err:
                best_i, best_err = i, err
        return best_i, best_err

    # TP1: prefer +tp target, else -stop
    tp1 = None
    for i in idxs:
        if parsed[i]["exit_reason"] == "target" and _near(parsed[i]["points"], tp, tol_tp):
            tp1 = i
            break
    if tp1 is None:
        i, err = closest(idxs, -abs(stop))
        if i is not None and err <= tol_stop:
            tp1 = i
    if tp1 is None:
        tp1 = min(idxs, key=lambda i: parsed[i]["exit_ts"])

    rest = [i for i in idxs if i != tp1]

    # 2R: prefer +2tp target among rest
    r2 = None
    for i in rest:
        if parsed[i]["exit_reason"] == "target" and _near(parsed[i]["points"], 2.0 * tp, tol_tp * 2):
            r2 = i
            break
    if r2 is None:
        # earlier exit among rest = short runner; later = long
        rest_sorted = sorted(rest, key=lambda i: (parsed[i]["exit_ts"], -abs(parsed[i]["points"])))
        r2, long_i = rest_sorted[0], rest_sorted[-1]
    else:
        long_i = [i for i in rest if i != r2][0]

    be_ts = ""
    if parsed[tp1]["exit_reason"] == "target" and _near(parsed[tp1]["points"], tp, tol_tp):
        be_ts = parsed[tp1]["exit_ts"]
    elif parsed[tp1].get("be_after_ts"):
        be_ts = parsed[tp1]["be_after_ts"]

    # Prefer explicit be_after_ts on long if present
    if parsed[long_i].get("be_after_ts"):
        be_ts = parsed[long_i]["be_after_ts"] or be_ts

    return [
        as_leg("tp1", parsed[tp1], be_ts),
        as_leg("runner_2r", parsed[r2], be_ts),
        as_leg("long", parsed[long_i], be_ts),
    ]


def _points_to_usd(points: float, *, instrument: str, is_jpy: bool, rate: float) -> float:
    if is_jpy:
        if rate <= 0:
            rate = 100.0
        return points * JPY_PV / rate - FEE_USD
    pv = float(POINT_VALUES.get(instrument, 1.0))
    return points * pv - FEE_USD


def _load_one_m(spec: MarketSpec) -> pd.DataFrame:
    gby = load_fx_1m_by_ny_date(spec.one_m_path, spec.instrument)
    df = concat_all_1m(gby)
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index, utc=True)
    # keep tz-aware iso matching unit fills
    return df.sort_index()


def _slice_1m(df: pd.DataFrame, start_ts: str, end_ts: str) -> pd.DataFrame:
    start = pd.Timestamp(start_ts)
    end = pd.Timestamp(end_ts)
    # align tz
    if df.index.tz is not None and start.tzinfo is None:
        start = start.tz_localize(df.index.tz)
        end = end.tz_localize(df.index.tz)
    elif df.index.tz is None and start.tzinfo is not None:
        start = start.tz_convert("UTC").tz_localize(None)
        end = end.tz_convert("UTC").tz_localize(None)
    return df.loc[(df.index >= start) & (df.index <= end)]


def _sim_long_all_k(
    leg: Leg,
    bars: pd.DataFrame,
    *,
    k_list: Sequence[Optional[float]],
    stop_pts: float,
    tp_pts: float,
    tick: float,
) -> Dict[Optional[float], SimExit]:
    """One bar pass → exit for every k (None = keep tape exit / indef)."""
    out: Dict[Optional[float], SimExit] = {}
    # Indef / tape baseline
    out[None] = SimExit(leg.exit_ts, leg.exit_price, leg.exit_reason, leg.points)
    finite = [float(k) for k in k_list if k is not None]
    if not finite:
        return out

    is_long = str(leg.direction).lower().startswith("l")
    entry = float(leg.entry_price)
    hard_stop = entry - stop_pts if is_long else entry + stop_pts
    be_stop = entry

    if bars is None or len(bars) == 0:
        for k in finite:
            out[k] = out[None]
        return out

    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    index = bars.index
    be_ts = None
    if leg.be_after_ts:
        be_ts = pd.Timestamp(leg.be_after_ts)
        if index.tz is not None and be_ts.tzinfo is None:
            be_ts = be_ts.tz_localize(index.tz)
        elif index.tz is None and be_ts.tzinfo is not None:
            be_ts = be_ts.tz_convert("UTC").tz_localize(None)
    targets = {k: (entry + k * tp_pts if is_long else entry - k * tp_pts) for k in finite}
    pending = set(finite)

    for i in range(len(index)):
        if not pending:
            break
        ts = index[i]
        o, h, l = opens[i], highs[i], lows[i]
        # BE applies only on bars *after* the TP1 fill bar. Same-bar OHLC can show
        # a pre-TP1 low below entry; activating BE on that bar falsely stops runners.
        after_be = bool(be_ts is not None and ts > be_ts)
        stop = be_stop if after_be else hard_stop
        if is_long:
            stop_hit = l <= stop
        else:
            stop_hit = h >= stop

        done_now = []
        for k in pending:
            target = targets[k]
            tgt_hit = (h >= target) if is_long else (l <= target)
            if stop_hit:
                fill = stop - tick if is_long else stop + tick
                if is_long and o < stop:
                    fill = o - tick
                if (not is_long) and o > stop:
                    fill = o + tick
                pts = (fill - entry) if is_long else (entry - fill)
                reason = "runner_stop" if after_be else "stop"
                out[k] = SimExit(ts.isoformat(), fill, reason, pts)
                done_now.append(k)
            elif tgt_hit:
                pts = (target - entry) if is_long else (entry - target)
                out[k] = SimExit(ts.isoformat(), target, "target", pts)
                done_now.append(k)
        for k in done_now:
            pending.discard(k)

    for k in pending:
        out[k] = out[None]
    return out


def _sim_long(
    leg: Leg,
    bars: pd.DataFrame,
    *,
    k: Optional[float],
    stop_pts: float,
    tp_pts: float,
    tick: float,
) -> SimExit:
    return _sim_long_all_k(
        leg, bars, k_list=[k], stop_pts=stop_pts, tp_pts=tp_pts, tick=tick
    )[k]


def _stress_from_units(
    units: Sequence[Tuple[str, str, str, float, float, float, str, float]],
    # (trade_id, role, direction, entry_ts, entry_px, exit_ts, exit_reason, points)
    hourly_closes: Optional[pd.Series],
    *,
    stop_pts: float,
    instrument: str,
    is_jpy: bool,
) -> float:
    """Reachable close-path stress in USD using hourly marks clipped to live stop."""
    if not units:
        return 0.0
    events = []
    for u in units:
        trade_id, role, direction, entry_ts, entry_px, exit_ts, exit_reason, points = u
        events.append((entry_ts, 1, u))
        events.append((exit_ts, 0, u))
    events.sort(key=lambda x: (x[0], x[1]))

    # Build sample timeline from unique timestamps
    times = sorted({e[0] for e in events})
    if hourly_closes is not None and len(hourly_closes):
        # also mark at hourly closes while anything open — approximate with event times only for speed
        pass

    active = []
    realized_pts = 0.0
    peak = 0.0
    min_dd_usd = 0.0
    ei = 0
    # Walk event times
    open_set = {}  # id -> unit
    uid = 0
    unit_ids = {}
    for ts, kind, u in events:
        if kind == 1:
            unit_ids[id(u)] = uid
            open_set[uid] = u
            uid += 1
        else:
            # realize
            _tid, _role, direction, entry_ts, entry_px, exit_ts, exit_reason, points = u
            realized_pts += points
            # remove matching open (by entry/exit identity)
            for k, ou in list(open_set.items()):
                if ou is u or (ou[3] == u[3] and ou[5] == u[5] and ou[1] == u[1] and ou[0] == u[0]):
                    open_set.pop(k, None)
                    break

        # mark open at ts
        mark_pts = realized_pts
        for ou in open_set.values():
            _tid, _role, direction, entry_ts, entry_px, exit_ts, exit_reason, points = ou
            is_long = str(direction).lower().startswith("l")
            # use exit price path unknown at intermediate — skip; stress from realized-only peaks
            # Better: use entry as mark 0 until exit (conservative understates adverse). 
            # Use clipped adverse: assume worst stop from entry for open units.
            be = False  # unknown mid-path; use hard stop distance as reachable adverse
            adverse = -stop_pts  # reachable worst vs entry before BE; after TP1 BE adverse ~0
            # If role long/runner and exit_reason suggests survived past tp1, BE risk ~0 once open after tp1
            # Approximate: open runner legs contribute 0 after their be; TP1 open contributes -stop
            if _role == "tp1":
                mark_pts += -stop_pts  # worst case while open
            else:
                mark_pts += 0.0  # BE runners ~0 stop risk after tp1; before tp1 same campaign usually co-stops

        # Convert DD using mid rate if jpy
        rate = 110.0
        if is_jpy and hourly_closes is not None:
            try:
                px = hourly_closes.get(ts)
                if px is not None and not (isinstance(px, float) and math.isnan(px)):
                    rate = float(px)
            except Exception:
                pass
        eq_usd = _points_to_usd(mark_pts, instrument=instrument, is_jpy=is_jpy, rate=rate) + len(units) * 0.0
        # fees already in per-unit; stress path uses points only then subtract fees at end
        eq_usd = (
            (mark_pts * JPY_PV / rate) if is_jpy else (mark_pts * float(POINT_VALUES.get(instrument, 1.0)))
        )
        if eq_usd > peak:
            peak = eq_usd
        min_dd_usd = min(min_dd_usd, eq_usd - peak)

    # Refine: compute stress from sequential unit equity using exit marks only (close path)
    peak = 0.0
    min_dd_usd = 0.0
    realized = 0.0
    ordered = sorted(units, key=lambda u: u[5])  # by exit_ts
    for u in ordered:
        _tid, _role, direction, entry_ts, entry_px, exit_ts, exit_reason, points = u
        rate = float(entry_px) if is_jpy else 1.0
        if is_jpy:
            try:
                # prefer exit price as rate for USDJPY
                rate = float(entry_px)  # USDJPY quote
            except Exception:
                rate = 110.0
        realized += points
        eq = (realized * JPY_PV / rate) if is_jpy else realized * float(POINT_VALUES.get(instrument, 1.0))
        if eq > peak:
            peak = eq
        min_dd_usd = min(min_dd_usd, eq - peak)
    return float(min_dd_usd)


def _reachable_stress_usd(
    sim_units: Sequence[dict],
    *,
    instrument: str,
    is_jpy: bool,
    stop_pts: float,
    one_m: pd.DataFrame,
) -> float:
    """Intrabar reachable stress: active units marked at adverse extreme clipped to live stop."""
    if not sim_units:
        return 0.0

    # Build list of Unit-like intervals
    intervals = []
    for u in sim_units:
        intervals.append(u)
    # Sample at 1m only while something is open — too heavy for full history.
    # Use event-based: at each entry/exit, and approximate open MTM with stop clip at those times.
    # Stronger: walk unique entry/exit timeline; for open units apply -remaining_stop_risk in points.

    times = sorted({u["entry_ts"] for u in intervals} | {u["exit_ts"] for u in intervals})
    peak = 0.0
    min_dd = 0.0
    for ts in times:
        realized = 0.0
        open_risk = 0.0
        rate = 110.0
        for u in intervals:
            if u["exit_ts"] < ts:
                realized += u["points"]
                if is_jpy:
                    rate = float(u.get("exit_rate") or u["entry_price"])
            elif u["entry_ts"] <= ts <= u["exit_ts"]:
                # reachable adverse = distance to live stop in points (signed already negative risk)
                is_long = str(u["direction"]).lower().startswith("l")
                entry = float(u["entry_price"])
                be_after = u.get("be_after_ts") or ""
                if be_after and ts > be_after:
                    live_stop = entry
                else:
                    live_stop = entry - stop_pts if is_long else entry + stop_pts
                # risk points if stopped now
                risk_pts = (live_stop - entry) if is_long else (entry - live_stop)
                open_risk += risk_pts
                if is_jpy:
                    rate = entry
        total_pts = realized + open_risk
        if is_jpy:
            eq = total_pts * JPY_PV / max(rate, 1e-9)
        else:
            eq = total_pts * float(POINT_VALUES.get(instrument, 1.0))
        if eq > peak:
            peak = eq
        min_dd = min(min_dd, eq - peak)
    return float(min_dd)


def _campaigns_from_indef(spec: MarketSpec) -> List[List[Leg]]:
    rows = _read_units(spec.indef_unit_fills)
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by[r["trade_id"]].append(r)
    campaigns = []
    for tid, units in by.items():
        campaigns.append(_classify_legs(units, spec.tp_pts, spec.stop_pts))
    return campaigns


def _entry_key(direction: str, entry_ts: str, entry_price: float) -> Tuple[str, str, float]:
    return (direction.lower()[0], entry_ts, round(float(entry_price), 4))


def _validate_k10(
    spec: MarketSpec,
    campaigns: Sequence[Sequence[Leg]],
    long_bars: Dict[str, pd.DataFrame],
) -> Dict[str, object]:
    """Compare postprocess long@10R to archived 2R→10R long legs on matched entries."""
    ref_rows = _read_units(spec.ref_10r_unit_fills)  # type: ignore[arg-type]
    ref_by: Dict[str, List[dict]] = defaultdict(list)
    for r in ref_rows:
        ref_by[r["trade_id"]].append(r)
    ref_long_by_entry: Dict[Tuple[str, str, float], float] = {}
    for tid, units in ref_by.items():
        legs = _classify_legs(units, spec.tp_pts, spec.stop_pts)
        long = next(l for l in legs if l.role == "long")
        ref_long_by_entry[_entry_key(long.direction, long.entry_ts, long.entry_price)] = long.points

    post_pts = 0.0
    ref_pts = 0.0
    matched = 0
    abs_err = 0.0
    for legs in campaigns:
        long = next(l for l in legs if l.role == "long")
        key = _entry_key(long.direction, long.entry_ts, long.entry_price)
        if key not in ref_long_by_entry:
            continue
        sim = _sim_long(
            long,
            long_bars[long.trade_id],
            k=10.0,
            stop_pts=spec.stop_pts,
            tp_pts=spec.tp_pts,
            tick=spec.tick,
        )
        rp = ref_long_by_entry[key]
        post_pts += sim.points
        ref_pts += rp
        abs_err += abs(sim.points - rp)
        matched += 1

    denom = abs(ref_pts) if ref_pts else 1.0
    ok = matched >= 10 and abs(post_pts - ref_pts) <= max(10.0, 0.08 * denom)
    return {
        "market": spec.key,
        "matched_campaigns": matched,
        "ref_campaigns": len(ref_long_by_entry),
        "post_long_points": round(post_pts, 4),
        "ref_long_points": round(ref_pts, 4),
        "long_points_diff": round(post_pts - ref_pts, 4),
        "mean_abs_err": round(abs_err / matched, 4) if matched else None,
        "ok_points": ok,
        # aliases for SUMMARY table
        "post_points": round(post_pts, 4),
        "ref_points": round(ref_pts, 4),
        "points_diff": round(post_pts - ref_pts, 4),
    }


def sweep_market(spec: MarketSpec, *, k_grid: Sequence[Optional[float]] = K_GRID) -> Dict[str, object]:
    if not spec.indef_unit_fills.exists():
        return {"market": spec.key, "status": "skipped_no_indef", "rows": []}

    print("Loading 1m for %s…" % spec.instrument, flush=True)
    one_m = _load_one_m(spec)
    print("  %s 1m bars=%d" % (spec.instrument, len(one_m)), flush=True)

    campaigns_raw = _campaigns_from_indef(spec)
    campaigns = []
    skipped_partial = 0
    for legs in campaigns_raw:
        roles = {l.role for l in legs}
        if not {"tp1", "runner_2r", "long"}.issubset(roles):
            skipped_partial += 1
            continue
        campaigns.append(legs)
    print(
        "  campaigns=%d (skipped_partial=%d)" % (len(campaigns), skipped_partial),
        flush=True,
    )

    # Pre-slice long legs' bars
    long_bars: Dict[str, pd.DataFrame] = {}
    for legs in campaigns:
        long = next(l for l in legs if l.role == "long")
        key = long.trade_id
        long_bars[key] = _slice_1m(one_m, long.entry_ts, long.exit_ts)

    # Per-campaign: freeze TP1/2R once; sim all k for long in one bar pass
    per_k_long: Dict[Optional[float], List[dict]] = {k: [] for k in k_grid}
    frozen_units: List[dict] = []
    frozen_pts_sum = 0.0
    frozen_usd_sum = 0.0
    frozen_wins = 0
    frozen_n = 0

    for legs in campaigns:
        by_role = {l.role: l for l in legs}
        tp1, r2, long = by_role["tp1"], by_role["runner_2r"], by_role["long"]
        for leg in (tp1, r2):
            rate = leg.exit_price if spec.is_jpy else 1.0
            usd = _points_to_usd(leg.points, instrument=spec.instrument, is_jpy=spec.is_jpy, rate=rate)
            frozen_usd_sum += usd
            frozen_pts_sum += leg.points
            frozen_n += 1
            if usd > 0:
                frozen_wins += 1
            frozen_units.append(
                {
                    "trade_id": leg.trade_id,
                    "role": leg.role,
                    "direction": leg.direction,
                    "entry_ts": leg.entry_ts,
                    "entry_price": leg.entry_price,
                    "exit_ts": leg.exit_ts,
                    "exit_reason": leg.exit_reason,
                    "points": leg.points,
                    "be_after_ts": leg.be_after_ts,
                    "exit_rate": leg.exit_price,
                }
            )
        sims = _sim_long_all_k(
            long,
            long_bars[long.trade_id],
            k_list=list(k_grid),
            stop_pts=spec.stop_pts,
            tp_pts=spec.tp_pts,
            tick=spec.tick,
        )
        for k in k_grid:
            sim = sims[k if k is None else float(k)]
            per_k_long[k].append(
                {
                    "trade_id": long.trade_id,
                    "role": "long",
                    "direction": long.direction,
                    "entry_ts": long.entry_ts,
                    "entry_price": long.entry_price,
                    "exit_ts": sim.exit_ts,
                    "exit_reason": sim.exit_reason,
                    "points": sim.points,
                    "be_after_ts": long.be_after_ts,
                    "exit_rate": sim.exit_price,
                }
            )

    rows_out = []
    validation = None
    for k in k_grid:
        k_label = "indef" if k is None else ("%.0f" % float(k) if float(k) == int(float(k)) else str(k))
        long_units = per_k_long[k]
        long_pts_sum = sum(u["points"] for u in long_units)
        long_usd = 0.0
        long_wins = 0
        for u in long_units:
            rate = u["exit_rate"] if spec.is_jpy else 1.0
            usd = _points_to_usd(u["points"], instrument=spec.instrument, is_jpy=spec.is_jpy, rate=rate)
            long_usd += usd
            if usd > 0:
                long_wins += 1
        net_usd = frozen_usd_sum + long_usd
        n_u = frozen_n + len(long_units)
        win_u = frozen_wins + long_wins
        sim_units = frozen_units + long_units
        stress = _reachable_stress_usd(
            sim_units,
            instrument=spec.instrument,
            is_jpy=spec.is_jpy,
            stop_pts=spec.stop_pts,
            one_m=one_m,
        )
        ns = (net_usd / abs(stress)) if stress else 0.0
        row = {
            "market": spec.key,
            "instrument": spec.instrument,
            "k": k_label,
            "k_num": "" if k is None else k,
            "net_usd": round(net_usd, 2),
            "stress_usd": round(stress, 2),
            "ns": round(ns, 3),
            "units": n_u,
            "wr_pct": round(100.0 * win_u / n_u, 1) if n_u else 0.0,
            "long_points": round(long_pts_sum, 4),
            "frozen_points": round(frozen_pts_sum, 4),
            "total_points": round(frozen_pts_sum + long_pts_sum, 4),
            "campaigns": len(campaigns),
            "fair_3r_ns": spec.fair_3r_ns,
            "beats_fair_3r_ns": ns > spec.fair_3r_ns,
        }
        rows_out.append(row)
        print(
            "  k=%-5s net=$%.0f stress=$%.0f N/S=%.2f long_pts=%.1f"
            % (k_label, net_usd, stress, ns, long_pts_sum),
            flush=True,
        )

    if spec.ref_10r_unit_fills and spec.ref_10r_unit_fills.exists():
        validation = _validate_k10(spec, campaigns, long_bars)
        print(
            "  VALIDATE k=10 matched=%s long_pts post=%.1f ref=%.1f diff=%.1f ok=%s"
            % (
                validation.get("matched_campaigns"),
                validation.get("post_long_points"),
                validation.get("ref_long_points"),
                validation.get("long_points_diff"),
                validation.get("ok_points"),
            ),
            flush=True,
        )

    # best rankable k (finite k preferred for inventory; include indef in table)
    finite = [r for r in rows_out if r["k"] != "indef"]
    best = max(finite, key=lambda r: r["ns"]) if finite else None
    best_indef = next((r for r in rows_out if r["k"] == "indef"), None)
    ref10 = next((r for r in rows_out if r["k"] == "10"), None)

    return {
        "market": spec.key,
        "status": "ok",
        "rows": rows_out,
        "validation": validation,
        "best_finite": best,
        "best_indef": best_indef,
        "ref_10r": ref10,
        "fair_3r_ns": spec.fair_3r_ns,
    }


def _json_sanitize(obj: object) -> object:
    """Make results JSON-safe without stringifying bools/None (breaks truthiness on reload)."""
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, (int, float, str)):
        return obj
    return str(obj)


def _as_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y"}
    return bool(v)


def _load_cached_result(market: str) -> Optional[Dict[str, object]]:
    path = OUT / market / "result.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    # Repair legacy caches that stringified bools via default=str
    if isinstance(data, dict):
        for row in data.get("rows") or []:
            if "beats_fair_3r_ns" in row:
                row["beats_fair_3r_ns"] = _as_bool(row["beats_fair_3r_ns"])
        for key in ("best_finite", "best_indef", "ref_10r"):
            blob = data.get(key)
            if isinstance(blob, dict) and "beats_fair_3r_ns" in blob:
                blob["beats_fair_3r_ns"] = _as_bool(blob["beats_fair_3r_ns"])
        val = data.get("validation")
        if isinstance(val, dict) and "ok_points" in val:
            val["ok_points"] = _as_bool(val["ok_points"])
    return data


def _write_ns_chart(mdir: Path, market: str, rows: Sequence[dict]) -> None:
    """N/S vs long-runner k (finite only); fair 3R reference line."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print("  chart skip (%s): %s" % (market, exc), flush=True)
        return
    finite = [r for r in rows if r.get("k") != "indef"]
    if not finite:
        return
    xs = [float(r["k_num"] if r.get("k_num") not in ("", None) else r["k"]) for r in finite]
    ys = [float(r["ns"]) for r in finite]
    fair = float(finite[0].get("fair_3r_ns") or 0.0)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(xs, ys, marker="o", color="#1f4e79", linewidth=1.8, label="runner book N/S")
    if fair:
        ax.axhline(fair, color="#b45f06", linestyle="--", linewidth=1.2, label="fair 3R N/S %.2f" % fair)
    ax.set_xlabel("long runner target k × TP1")
    ax.set_ylabel("USD-normalized N/S")
    ax.set_title("%s long-runner length sweep" % market.upper())
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    out = mdir / "ns_vs_k.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("  chart %s" % out, flush=True)


def write_hub(results: Sequence[Dict[str, object]], *, merge_cached: bool = True) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_market: Dict[str, Dict[str, object]] = {}
    if merge_cached:
        for spec in _market_specs():
            cached = _load_cached_result(spec.key)
            if cached and cached.get("status") == "ok" and cached.get("rows"):
                by_market[spec.key] = cached
    for res in results:
        mdir = OUT / str(res["market"])
        mdir.mkdir(parents=True, exist_ok=True)
        if res.get("rows"):
            fields = list(res["rows"][0].keys())
            with (mdir / "sweep.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                w.writerows(res["rows"])
            _write_ns_chart(mdir, str(res["market"]), res["rows"])
        (mdir / "result.json").write_text(
            json.dumps(_json_sanitize(res), indent=2, sort_keys=True) + "\n"
        )
        if res.get("status") == "ok" and res.get("rows"):
            by_market[str(res["market"])] = res
        elif res.get("status") == "skipped_no_indef":
            # keep prior ok cache; record skip only if nothing cached
            by_market.setdefault(str(res["market"]), res)

    ordered = []
    for spec in _market_specs():
        if spec.key in by_market:
            ordered.append(by_market[spec.key])
    for m, res in by_market.items():
        if res not in ordered:
            ordered.append(res)

    all_rows = []
    for res in ordered:
        for r in res.get("rows") or []:
            all_rows.append(r)

    if all_rows:
        fields = list(all_rows[0].keys())
        with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(all_rows)

    pending = [
        s.key
        for s in _market_specs()
        if not s.indef_unit_fills.exists()
        or (by_market.get(s.key) or {}).get("status") == "skipped_no_indef"
    ]

    lines = [
        "# ST+PMC long-runner length sweep (postprocess)",
        "",
        "Source: `*_runners_2r_indef` tapes (US30 prefers `audits_lot_correct`).",
        "Structure: TP1 + fixed 2R + long@k×TP1 (BE after TP1; BE starts the bar *after* TP1 fill).",
        "Grid: k ∈ {2,3,4,5,6,7,8,9,10,12,15,indef}. JPY → USD normalized.",
        "",
        "## Validation (k=10 vs archived 2R→10R)",
        "",
        "| market | post pts | ref pts | diff | ok |",
        "|---|---:|---:|---:|---|",
    ]
    for res in ordered:
        v = res.get("validation")
        if not v:
            lines.append("| `%s` | — | — | — | %s |" % (res["market"], res.get("status", "skipped")))
            continue
        lines.append(
            "| `%s` | %.1f | %.1f | %.1f | %s |"
            % (
                v["market"],
                v["post_points"],
                v["ref_points"],
                v["points_diff"],
                "**yes**" if _as_bool(v.get("ok_points")) else "NO",
            )
        )

    lines += ["", "## Best finite k by N/S", "", "| market | best k | N/S | net | stress | vs 3R | vs 10R |", "|---|---:|---:|---:|---:|---|---|"]
    for res in ordered:
        b = res.get("best_finite")
        r10 = res.get("ref_10r")
        if not b:
            lines.append("| `%s` | — | — | — | — | %s | — |" % (res["market"], res.get("status")))
            continue
        vs3 = "YES" if _as_bool(b.get("beats_fair_3r_ns")) else "no"
        vs10 = "—"
        if r10:
            vs10 = "YES" if float(b["ns"]) > float(r10["ns"]) else "no"
        lines.append(
            "| `%s` | **%s** | **%.2f** | $%.0f | $%.0f | %s | %s |"
            % (b["market"], b["k"], b["ns"], b["net_usd"], b["stress_usd"], vs3, vs10)
        )

    if pending:
        lines += [
            "",
            "## Queued (waiting on indef tape)",
            "",
            ", ".join("`%s`" % m for m in pending),
            "",
            "Postprocess appends automatically when `*_runners_2r_indef` unit_fills appear; no parallel StrategyPlugin rerun.",
        ]

    lines += ["", "## Full grid", "", "| market | k | net | stress | N/S | long pts | beats 3R? |", "|---|---:|---:|---:|---:|---:|---|"]
    for r in all_rows:
        lines.append(
            "| `%s` | %s | $%.0f | $%.0f | %.2f | %.1f | %s |"
            % (
                r["market"],
                r["k"],
                r["net_usd"],
                r["stress_usd"],
                r["ns"],
                r["long_points"],
                "yes" if _as_bool(r.get("beats_fair_3r_ns")) else "",
            )
        )

    promote = []
    for res in ordered:
        b = res.get("best_finite")
        r10 = res.get("ref_10r")
        if not b or not r10:
            continue
        if _as_bool(b.get("beats_fair_3r_ns")) and float(b["ns"]) > float(r10["ns"]):
            promote.append("%s k=%s (N/S %.2f)" % (b["market"], b["k"], b["ns"]))

    lines += [
        "",
        "## Notes",
        "",
        "- Fair 3R alone cannot answer runner length (flat at TP1).",
        "- 2R→10R censors k>10; indef tape is the uncensored source.",
        "- Promote a k only if it beats **both** fair 3R N/S and k=10 N/S with max open 3.",
        "- Promotion candidates this run: %s." % (", ".join(promote) if promote else "none"),
        "",
        "## Artifacts",
        "",
        "- `summary.csv`",
        "- Per market: `<market>/sweep.csv`, `<market>/result.json`, `<market>/ns_vs_k.png`",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    keys = [s.key for s in _market_specs()]
    ap.add_argument("--markets", nargs="*", default=None, choices=keys)
    ap.add_argument("--skip-missing", action="store_true", default=True)
    ap.add_argument(
        "--wait-missing",
        action="store_true",
        help="Poll until requested markets have indef unit_fills, then sweep them.",
    )
    ap.add_argument("--poll-sec", type=float, default=120.0)
    ap.add_argument("--wait-timeout-sec", type=float, default=0.0, help="0 = wait forever")
    args = ap.parse_args(list(argv) if argv is not None else None)

    want = set(args.markets) if args.markets else None
    specs = [s for s in _market_specs() if want is None or s.key in want]

    def _needs_sweep(spec: MarketSpec) -> bool:
        if not spec.indef_unit_fills.exists():
            return False
        cached = _load_cached_result(spec.key)
        return not (cached and cached.get("status") == "ok" and cached.get("rows"))

    results: List[Dict[str, object]] = []
    if args.wait_missing:
        import time

        t0 = time.time()
        done: set = set()
        while True:
            pending = [s for s in specs if s.key not in done and not s.indef_unit_fills.exists()]
            ready = [s for s in specs if s.key not in done and _needs_sweep(s)]
            for spec in ready:
                print("SWEEP %s" % spec.key, flush=True)
                res = sweep_market(spec)
                results.append(res)
                write_hub(results, merge_cached=True)
                done.add(spec.key)
            # already-cached ok
            for spec in specs:
                if spec.key in done:
                    continue
                cached = _load_cached_result(spec.key)
                if cached and cached.get("status") == "ok" and cached.get("rows"):
                    print("KEEP cached %s" % spec.key, flush=True)
                    results.append(cached)
                    done.add(spec.key)
            if len(done) >= len(specs):
                break
            if not pending and not ready:
                break
            print("WAIT indef: %s" % ", ".join(s.key for s in pending), flush=True)
            if args.wait_timeout_sec and (time.time() - t0) > args.wait_timeout_sec:
                print("WAIT timeout; hub has ready markets only", flush=True)
                for spec in pending:
                    results.append({"market": spec.key, "status": "skipped_no_indef", "rows": []})
                break
            time.sleep(max(5.0, float(args.poll_sec)))
        write_hub(results, merge_cached=True)
        return 0

    for spec in specs:
        if not spec.indef_unit_fills.exists():
            print("SKIP %s — no indef unit_fills yet" % spec.key, flush=True)
            results.append({"market": spec.key, "status": "skipped_no_indef", "rows": []})
            continue
        print("SWEEP %s" % spec.key, flush=True)
        results.append(sweep_market(spec))
    write_hub(results, merge_cached=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
