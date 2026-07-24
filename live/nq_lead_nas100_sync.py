"""NQ-lead → NAS100 sync helpers (campaign load + OR mapping).

Used by the ``v2b_nq_lead_nas100`` strategy and its broker-like replay driver.
Does not modify standalone NQ or NAS100 prior-opposed paths.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd
import pytz

NY = pytz.timezone("America/New_York")
NQ_TICK = 0.25


def _to_ny(ts: Any) -> datetime:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.to_pydatetime()


def _parse_ny_iso(ts: str) -> datetime:
    return _to_ny(ts)


def load_nq_lead_campaigns(
    nq_state_root: Path,
    *,
    strategy_id: str = "nq_v2b_prior_opposed_stpmc_only_S_1_1_3",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build session-keyed lead campaigns from an NQ prior-opposed state root.

    OR levels are inferred from filled entry stops + wide stops when present:
    - Long entry stop ≈ OR high + tick → ``or_high_nq = stop - tick``
    - Long wide stop ≈ OR low
    - Short mirrored.
    """

    states = nq_state_root / "states" / strategy_id
    units_path = states / "unit_trades.csv"
    orders_path = states / "orders.csv"
    if not units_path.exists():
        raise FileNotFoundError(units_path)

    by_trade: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    with units_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            by_trade[str(row["trade_id"])].append(row)

    entry_orders: Dict[str, Dict[str, str]] = {}
    wide_stops: Dict[str, Dict[str, str]] = {}
    if orders_path.exists():
        with orders_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                tid = str(row.get("trade_id") or "")
                role = str(row.get("bracket_role") or "")
                if role == "entry" and tid not in entry_orders:
                    entry_orders[tid] = row
                if role == "wide_stop" and tid not in wide_stops:
                    wide_stops[tid] = row

    out: Dict[str, List[Dict[str, Any]]] = {}
    for tid, units in by_trade.items():
        units = sorted(units, key=lambda u: u["entry_ts"])
        first = units[0]
        entry_ts = _to_ny(first["entry_ts"])
        session = entry_ts.date()
        if start is not None and session < start:
            continue
        if end is not None and session > end:
            continue

        side_raw = str(first["direction"]).lower()
        side = "long" if side_raw.startswith("l") else "short"
        p_nq = float(first["entry_price"])

        or_high: Optional[float] = None
        or_low: Optional[float] = None
        ent = entry_orders.get(tid)
        wide = wide_stops.get(tid)
        if ent is not None and ent.get("stop_price") not in (None, ""):
            stop = float(ent["stop_price"])
            if side == "long":
                or_high = stop - NQ_TICK
            else:
                or_low = stop + NQ_TICK
        if wide is not None and wide.get("stop_price") not in (None, ""):
            wpx = float(wide["stop_price"])
            if side == "long":
                or_low = wpx
            else:
                or_high = wpx
        # Fallback: synthetic 1R band around entry if OR incomplete.
        if or_high is None and or_low is None:
            band = 25.0
            or_high = p_nq + (band if side == "long" else 0.0)
            or_low = p_nq - (band if side == "short" else 0.0)
            if side == "long":
                or_low = p_nq - band
            else:
                or_high = p_nq + band
        elif or_high is None and or_low is not None:
            or_high = or_low + max(25.0, abs(p_nq - or_low))
        elif or_low is None and or_high is not None:
            or_low = or_high - max(25.0, abs(or_high - p_nq))

        t_tp1: Optional[str] = None
        t_stop: Optional[str] = None
        t_eod: Optional[str] = None
        for u in units:
            reason = str(u.get("exit_reason") or "")
            ets = str(u.get("exit_ts") or "")
            if reason == "tp1" and t_tp1 is None:
                t_tp1 = ets
            elif reason in {"wide_stop", "runner_stop"} and t_stop is None:
                t_stop = ets
            elif reason == "eod_close" and t_eod is None:
                t_eod = ets

        event = {
            "campaign_id": tid,
            "side": side,
            "t_nq_entry": entry_ts.isoformat(),
            "p_nq_entry": p_nq,
            "or_high_nq": float(or_high),
            "or_low_nq": float(or_low),
            "t_nq_tp1": t_tp1,
            "t_nq_stop": t_stop,
            "t_nq_eod": t_eod,
        }
        out.setdefault(session.isoformat(), []).append(event)

    for session in out:
        out[session].sort(key=lambda e: e["t_nq_entry"])
    return out


def attach_mapped_or(
    campaigns_by_session: Dict[str, List[Dict[str, Any]]],
    nas_bars_by_date: Mapping[date, pd.DataFrame],
) -> Dict[str, List[Dict[str, Any]]]:
    """Add ``mapped_or_high`` / ``mapped_or_low`` via NAS/NQ price ratio at NQ entry."""

    enriched: Dict[str, List[Dict[str, Any]]] = {}
    for session, events in campaigns_by_session.items():
        day = date.fromisoformat(session)
        day_bars = nas_bars_by_date.get(day)
        rows: List[Dict[str, Any]] = []
        for ev in events:
            ev2 = dict(ev)
            t_nq = _parse_ny_iso(str(ev["t_nq_entry"]))
            p_nq = float(ev["p_nq_entry"])
            nas_px = _nas_mid_at(day_bars, t_nq)
            if nas_px is None or p_nq <= 0:
                # Leave unmapped; plugin will skip for failed structure.
                ev2["mapped_or_high"] = None
                ev2["mapped_or_low"] = None
                ev2["map_ratio"] = None
            else:
                ratio = float(nas_px) / float(p_nq)
                ev2["map_ratio"] = ratio
                ev2["mapped_or_high"] = float(ev["or_high_nq"]) * ratio
                ev2["mapped_or_low"] = float(ev["or_low_nq"]) * ratio
                ev2["p_nas_at_nq_entry"] = float(nas_px)
            rows.append(ev2)
        enriched[session] = rows
    return enriched


def _nas_mid_at(day_bars: Optional[pd.DataFrame], t_nq: datetime) -> Optional[float]:
    if day_bars is None or day_bars.empty:
        return None
    idx = day_bars.index
    # nearest bar at or before t_nq; else first after
    try:
        pos = idx.searchsorted(pd.Timestamp(t_nq), side="right") - 1
    except Exception:
        return None
    if pos < 0:
        pos = 0
    if pos >= len(day_bars):
        pos = len(day_bars) - 1
    row = day_bars.iloc[pos]
    return float(row["close"])


def campaigns_for_json(campaigns_by_session: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """JSON-safe copy (None → null handled by json.dumps)."""

    out: Dict[str, List[Dict[str, Any]]] = {}
    for session, rows in campaigns_by_session.items():
        out[session] = [dict(r) for r in rows]
    return out
