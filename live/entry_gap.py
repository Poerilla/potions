"""Resting entry limit gap rules (overnight / session open).

Used by PaperBroker and monthly-open sidecars so gap-through and adverse
session opens do not fill limits we could not realistically place.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def session_gap(prev_ts: str, ts: str, *, min_gap_minutes: float = 45.0) -> bool:
    """True when bar timestamps imply an overnight / weekend break."""
    if not prev_ts or not ts:
        return False
    a = pd.Timestamp(prev_ts)
    b = pd.Timestamp(ts)
    if a.tzinfo is None:
        a = a.tz_localize("UTC")
    if b.tzinfo is None:
        b = b.tz_localize("UTC")
    return (b - a).total_seconds() > float(min_gap_minutes) * 60.0


def gapped_through(side: str, entry: float, prev_close: float, bar_open: float) -> bool:
    """Prior close on approach side and session open gaps through the limit."""
    if side == "buy" or side == "long":
        return prev_close > entry and bar_open < entry
    return prev_close < entry and bar_open > entry


def adverse_open(side: str, entry: float, bar_open: float) -> bool:
    """Open is on the wrong side of the entry (gap against the trade)."""
    if side == "buy" or side == "long":
        return bar_open < entry
    return bar_open > entry


def adverse_open_near_stop(
    side: str,
    entry: float,
    stop: float,
    bar_open: float,
    *,
    near_sl_frac: float = 0.15,
) -> bool:
    """Adverse session open and price is already at/near the protective stop."""
    if not adverse_open(side, entry, bar_open):
        return False
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return True
    if side == "buy" or side == "long":
        if bar_open <= stop:
            return True
        return (float(entry) - float(bar_open)) >= (1.0 - float(near_sl_frac)) * risk
    if bar_open >= stop:
        return True
    return (float(bar_open) - float(entry)) >= (1.0 - float(near_sl_frac)) * risk


def entry_limit_gap_blocked(
    *,
    side: str,
    entry: float,
    stop: Optional[float],
    prev_close: Optional[float],
    bar_open: float,
    session_gap: bool,
    near_sl_frac: float = 0.15,
) -> bool:
    """Return True when a resting entry limit must not fill on this bar open."""
    if not session_gap or prev_close is None:
        return False
    pc = float(prev_close)
    op = float(bar_open)
    ent = float(entry)
    if gapped_through(side, ent, pc, op):
        return True
    if stop is not None and adverse_open_near_stop(side, ent, float(stop), op, near_sl_frac=near_sl_frac):
        return True
    if adverse_open(side, ent, op) and abs(op - pc) > 1e-9:
        # Any adverse gap at session open — wait for retag.
        return True
    return False
