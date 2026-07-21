"""EURUSD Monday opening-range breakout on 15m bars.

Rules
-----
- Monday NY OR: high / low. Trade Tue 00:00 → Fri end NY (no day filter).
- Long: 15m close > Monday high; Short: 15m close < Monday low.
- R = Monday high − Monday low.
- Enter **3 units**. Stop = entry ∓ 1R; target = entry ± reward_R × R (default 2R).
- DD cuts (fraction of way entry→stop): drop **2** @ **30%**; cut last **1** @ **50%**
  (no runner past 50%).
- **HTF filter (default on):** skip entry when last 1h bar has **both** MA50/150 and
  OBV vs OBV-SMA20 opposed to the trade.
- Optional **reverse fade (parallel):** when flattened at 50% DD, enter **3 units** opposite
  at the **flat price** with the same DD structure (drop 2@30%, cut 1@50%). Fade does **not**
  block the next primary breakout.
- Optional **shifted primary (replaces fade intent):** when flattened at 50% DD, wait for
  the **opposite Monday extreme** breakout (failed MonH long → short at MonL; failed MonL
  short → long at MonH) with the **same** 3 / drop2@30 / cut1@50 / 1R–2R structure. Levels
  are shifted by exactly one Monday range. Does not count toward max primary trades/week;
  resumes primary scan after the shifted trade exits (or week ends with no fill).
- Max **2** primary breakout trades/week.
- Fee $1.50 / unit round-turn; point value $100k.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
POINT_VALUE = 100_000.0
FEE = 1.50
DEFAULT_OUT = REPO / "live" / "state" / "eurusd_monday_or_breakout_15m"
CONTRACTS = 3
DD_CUTS: Tuple[Tuple[float, int], ...] = ((0.30, 2), (0.50, 1))
OBV_MA = 20


def resample_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def build_htf_features(df_1m: pd.DataFrame, *, obv_ma: int = OBV_MA) -> pd.DataFrame:
    h1 = resample_1h(df_1m)
    h1["ma50"] = h1["close"].rolling(50, min_periods=50).mean()
    h1["ma150"] = h1["close"].rolling(150, min_periods=150).mean()
    h1["ma_bull"] = h1["ma50"] > h1["ma150"]
    direction = np.sign(h1["close"].diff()).fillna(0.0)
    vol = h1["volume"].fillna(0.0).clip(lower=0.0)
    proxy = (h1["high"] - h1["low"]).clip(lower=1e-8)
    use_vol = vol.where(vol > 0, proxy)
    h1["obv"] = (direction * use_vol).cumsum()
    h1["obv_ma"] = h1["obv"].rolling(obv_ma, min_periods=obv_ma).mean()
    h1["obv_bull"] = h1["obv"] > h1["obv_ma"]
    return h1


def htf_both_opposed(h1: pd.DataFrame, ts: pd.Timestamp, side: str) -> bool:
    """True if last completed 1h bar has MA and OBV both opposed to ``side``."""
    if h1 is None or h1.empty:
        return False
    # last bar with start <= ts
    idx = h1.index
    pos = idx.searchsorted(ts, side="right") - 1
    if pos < 0:
        return False
    row = h1.iloc[pos]
    if not (np.isfinite(row["ma50"]) and np.isfinite(row["ma150"]) and np.isfinite(row["obv_ma"])):
        return False
    ma_bull = bool(row["ma_bull"])
    obv_bull = bool(row["obv_bull"])
    if side == "long":
        return (not ma_bull) and (not obv_bull)
    return ma_bull and obv_bull


@dataclass
class Trade:
    week_monday: str
    side: str
    entry_ts: str
    exit_ts: str
    entry: float
    exit: float
    stop: float
    target: float
    dd30_px: float
    dd50_px: float
    dd30_exit: float
    dd30_ts: str
    dd50_exit: float
    dd50_ts: str
    cut_30: int
    cut_50: int
    monday_high: float
    monday_low: float
    R: float
    pnl_usd: float
    result: str
    exit_reason: str
    trade_num_in_week: int
    contracts: int
    is_reverse_fade: int
    is_shifted_primary: int
    parent_entry_ts: str


def resample_15m(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("15min", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def week_bounds(monday: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    m = pd.Timestamp(monday)
    if m.tzinfo is None:
        m = NY_TZ.localize(m.to_pydatetime())
    else:
        m = m.tz_convert(NY)
    mon0 = NY_TZ.localize(datetime.combine(m.date(), time(0, 0)))
    while mon0.weekday() != 0:
        mon0 -= timedelta(days=1)
    tue0 = mon0 + timedelta(days=1)
    sat0 = mon0 + timedelta(days=5)
    return pd.Timestamp(mon0), pd.Timestamp(tue0), pd.Timestamp(sat0)


def list_mondays(m15: pd.DataFrame) -> List[pd.Timestamp]:
    idx = m15.index
    out: List[pd.Timestamp] = []
    seen = set()
    for ts in idx[::64]:
        ny = ts.tz_convert(NY)
        mon0 = NY_TZ.localize(datetime.combine(ny.date(), time(0, 0)))
        while mon0.weekday() != 0:
            mon0 -= timedelta(days=1)
        mon0 = pd.Timestamp(mon0)
        key = int(mon0.value)
        if key in seen:
            continue
        seen.add(key)
        _, _, sat0 = week_bounds(mon0)
        if sat0 > idx[-1] + timedelta(minutes=15):
            continue
        mon_bars = m15[(m15.index >= mon0) & (m15.index < mon0 + timedelta(days=1))]
        if len(mon_bars) < 8:
            continue
        out.append(mon0)
    return out


def _signed_pnl_pts(side: str, entry: float, exit_px: float) -> float:
    return (exit_px - entry) if side == "long" else (entry - exit_px)


def _manage_dd_scale(
    rest: pd.DataFrame,
    start_j: int,
    *,
    side: str,
    entry: float,
    stop: float,
    target: float,
    contracts: int,
    dd_cuts: Sequence[Tuple[float, int]] = DD_CUTS,
) -> Tuple[float, pd.Timestamp, float, str, int, dict]:
    """Same structure as primary: N in, DD cuts, no runner past last cut."""
    cuts_sched = sorted([(float(f), int(u)) for f, u in dd_cuts], key=lambda x: x[0])
    if side == "long":
        risk = entry - stop
        cut_px = [entry - f * risk for f, _ in cuts_sched]
    else:
        risk = stop - entry
        cut_px = [entry + f * risk for f, _ in cuts_sched]

    remaining = contracts
    cut_done = [False] * len(cuts_sched)
    cut_exit_px = [float("nan")] * len(cuts_sched)
    cut_exit_ts = [""] * len(cuts_sched)
    cut_units_done = [0] * len(cuts_sched)
    pnl_usd = 0.0
    exit_px = None
    exit_ts = None
    exit_reason = None
    n = len(rest)
    j = start_j

    def apply_cuts(hit_flags: List[bool], bts) -> None:
        nonlocal remaining, pnl_usd
        for k, ((frac, units), px, hit) in enumerate(zip(cuts_sched, cut_px, hit_flags)):
            if cut_done[k] or not hit or remaining <= 0:
                continue
            take = min(units, remaining)
            if take <= 0:
                continue
            pnl_usd += take * (_signed_pnl_pts(side, entry, px) * POINT_VALUE - FEE)
            remaining -= take
            cut_done[k] = True
            cut_exit_px[k] = px
            cut_exit_ts[k] = str(bts)
            cut_units_done[k] = take

    while j < n and remaining > 0:
        bar = rest.iloc[j]
        hi = float(bar["high"])
        lo = float(bar["low"])
        bts = rest.index[j]
        if side == "long":
            hit_stop = lo <= stop
            hit_flags = [lo <= px for px in cut_px]
            hit_tgt = hi >= target
        else:
            hit_stop = hi >= stop
            hit_flags = [hi >= px for px in cut_px]
            hit_tgt = lo <= target

        if hit_stop:
            apply_cuts(hit_flags, bts)
            if remaining > 0:
                pnl_usd += remaining * (_signed_pnl_pts(side, entry, stop) * POINT_VALUE - FEE)
                remaining = 0
                tags = (["dd_cut"] if any(cut_done) else []) + ["stop"]
                exit_reason = "+".join(tags)
                exit_px = stop
            else:
                exit_reason = "dd_cut+flat_at_50"
                exit_px = cut_px[-1] if cut_done[-1] else stop
            exit_ts = bts
            break

        apply_cuts(hit_flags, bts)
        if remaining == 0:
            exit_px = cut_exit_px[-1] if cut_done[-1] else cut_exit_px[0]
            exit_ts = bts
            exit_reason = "dd_cut+flat_at_50"
            break

        if hit_tgt:
            pnl_usd += remaining * (_signed_pnl_pts(side, entry, target) * POINT_VALUE - FEE)
            remaining = 0
            tags = (["dd_cut"] if any(cut_done) else []) + ["target"]
            exit_reason = "+".join(tags)
            exit_px, exit_ts = target, bts
            break
        j += 1

    if remaining > 0:
        last = rest.iloc[-1]
        flat_px = float(last["close"])
        flat_ts = rest.index[-1]
        pnl_usd += remaining * (_signed_pnl_pts(side, entry, flat_px) * POINT_VALUE - FEE)
        remaining = 0
        tags = (["dd_cut"] if any(cut_done) else []) + ["week_end"]
        exit_reason = "+".join(tags)
        exit_px, exit_ts = flat_px, flat_ts
        j = n - 1

    assert exit_px is not None and exit_ts is not None and exit_reason is not None
    meta = {
        "cut_px": cut_px,
        "cut_done": cut_done,
        "cut_exit_px": cut_exit_px,
        "cut_exit_ts": cut_exit_ts,
        "cut_units_done": cut_units_done,
        "cuts_sched": cuts_sched,
    }
    return float(pnl_usd), exit_ts, float(exit_px), exit_reason, j, meta


def _trade_result(exit_reason: str, pnl_usd: float) -> str:
    if exit_reason.endswith("target"):
        return "win"
    if exit_reason.endswith("stop") or exit_reason.endswith("flat_at_50"):
        return "loss"
    return "win" if pnl_usd > 0 else "loss"


def _cuts_from_meta(meta: dict) -> Tuple[int, int, float, float, str, str, float, float]:
    cut_30 = cut_50 = 0
    dd30 = dd50 = float("nan")
    dd30_x = dd50_x = float("nan")
    dd30_ts = dd50_ts = ""
    for ck, (frac, _) in enumerate(meta["cuts_sched"]):
        px = meta["cut_px"][ck]
        if abs(frac - 0.30) < 1e-9:
            dd30 = px
            if meta["cut_done"][ck]:
                cut_30 = meta["cut_units_done"][ck]
                dd30_x = meta["cut_exit_px"][ck]
                dd30_ts = meta["cut_exit_ts"][ck]
        if abs(frac - 0.50) < 1e-9:
            dd50 = px
            if meta["cut_done"][ck]:
                cut_50 = meta["cut_units_done"][ck]
                dd50_x = meta["cut_exit_px"][ck]
                dd50_ts = meta["cut_exit_ts"][ck]
    return cut_30, cut_50, dd30, dd50, dd30_ts, dd50_ts, dd30_x, dd50_x


def simulate_week(
    m15: pd.DataFrame,
    monday: pd.Timestamp,
    *,
    max_trades: int = 2,
    reward_R: float = 2.0,
    contracts: int = CONTRACTS,
    dd_cuts: Sequence[Tuple[float, int]] = DD_CUTS,
    reverse_fade: bool = False,
    reverse_fade_units: int = CONTRACTS,
    shifted_primary: bool = False,
    shifted_contracts: Optional[int] = None,
    shifted_dd_cuts: Optional[Sequence[Tuple[float, int]]] = None,
    h1: Optional[pd.DataFrame] = None,
    skip_both_opposed: bool = True,
) -> List[Trade]:
    mon0, tue0, sat0 = week_bounds(monday)
    monday_bars = m15[(m15.index >= mon0) & (m15.index < tue0)]
    if monday_bars.empty:
        return []
    mon_high = float(monday_bars["high"].max())
    mon_low = float(monday_bars["low"].min())
    R = mon_high - mon_low
    if not np.isfinite(R) or R <= 1e-5:
        return []

    rest = m15[(m15.index >= tue0) & (m15.index < sat0)]
    trades: List[Trade] = []
    i = 0
    n = len(rest)
    primary_count = 0
    # Mutually exclusive: shifted primary replaces fade sidecar
    use_fade = reverse_fade and not shifted_primary
    pending_shift_side: Optional[str] = None
    pending_shift_parent = ""
    shift_qty = int(shifted_contracts if shifted_contracts is not None else contracts)
    shift_cuts = shifted_dd_cuts if shifted_dd_cuts is not None else dd_cuts

    while i < n and (primary_count < max_trades or pending_shift_side is not None):
        row = rest.iloc[i]
        ts = rest.index[i]
        close = float(row["close"])

        # Armed shifted sidecar: opposite Mon extreme owns that breakout signal
        if pending_shift_side is not None:
            hit = (
                (close < mon_low)
                if pending_shift_side == "short"
                else (close > mon_high)
            )
            if hit and not (
                skip_both_opposed and htf_both_opposed(h1, ts, pending_shift_side)
            ):
                s_entry = close
                if pending_shift_side == "long":
                    s_stop = s_entry - R
                    s_tgt = s_entry + reward_R * R
                else:
                    s_stop = s_entry + R
                    s_tgt = s_entry - reward_R * R
                spnl, s_exit_ts, s_exit_px, s_reason, s_end, smeta = _manage_dd_scale(
                    rest,
                    i + 1,
                    side=pending_shift_side,
                    entry=s_entry,
                    stop=s_stop,
                    target=s_tgt,
                    contracts=shift_qty,
                    dd_cuts=shift_cuts,
                )
                s_result = _trade_result(s_reason, spnl)
                (
                    s_cut_30,
                    s_cut_50,
                    s_dd30,
                    s_dd50,
                    s_dd30_ts,
                    s_dd50_ts,
                    s_dd30_x,
                    s_dd50_x,
                ) = _cuts_from_meta(smeta)
                trades.append(
                    Trade(
                        week_monday=mon0.strftime("%Y-%m-%d"),
                        side=pending_shift_side,
                        entry_ts=str(ts),
                        exit_ts=str(s_exit_ts),
                        entry=s_entry,
                        exit=float(s_exit_px),
                        stop=s_stop,
                        target=s_tgt,
                        dd30_px=float(s_dd30),
                        dd50_px=float(s_dd50),
                        dd30_exit=s_dd30_x,
                        dd30_ts=s_dd30_ts,
                        dd50_exit=s_dd50_x,
                        dd50_ts=s_dd50_ts,
                        cut_30=s_cut_30,
                        cut_50=s_cut_50,
                        monday_high=mon_high,
                        monday_low=mon_low,
                        R=R,
                        pnl_usd=float(spnl),
                        result=s_result,
                        exit_reason="shifted_primary+" + s_reason,
                        trade_num_in_week=primary_count,
                        contracts=shift_qty,
                        is_reverse_fade=0,
                        is_shifted_primary=1,
                        parent_entry_ts=pending_shift_parent,
                    )
                )
                pending_shift_side = None
                pending_shift_parent = ""
                i = s_end + 1
                continue
            # Opposite extreme reserved while armed — skip as primary
            if (pending_shift_side == "short" and close < mon_low) or (
                pending_shift_side == "long" and close > mon_high
            ):
                i += 1
                continue

        if primary_count >= max_trades:
            if pending_shift_side is None:
                break
            i += 1
            continue

        side = None
        if close > mon_high:
            side = "long"
        elif close < mon_low:
            side = "short"
        if side is None:
            i += 1
            continue
        # Don't take primary on the level reserved for an armed shift
        if pending_shift_side is not None and side == pending_shift_side:
            i += 1
            continue

        # Most effective HTF filter: skip when both 1h MA and OBV opposed
        if skip_both_opposed and htf_both_opposed(h1, ts, side):
            i += 1
            continue

        entry = close
        if side == "long":
            stop = entry - R
            target = entry + reward_R * R
        else:
            stop = entry + R
            target = entry - reward_R * R

        pnl_usd, exit_ts, exit_px, exit_reason, j, meta = _manage_dd_scale(
            rest,
            i + 1,
            side=side,
            entry=entry,
            stop=stop,
            target=target,
            contracts=contracts,
            dd_cuts=dd_cuts,
        )
        result = _trade_result(exit_reason, pnl_usd)
        cut_30, cut_50, dd30_px, dd50_px, dd30_ts, dd50_ts, dd30_exit, dd50_exit = _cuts_from_meta(
            meta
        )

        primary_count += 1
        parent_ts = str(ts)
        trades.append(
            Trade(
                week_monday=mon0.strftime("%Y-%m-%d"),
                side=side,
                entry_ts=parent_ts,
                exit_ts=str(exit_ts),
                entry=entry,
                exit=float(exit_px),
                stop=stop,
                target=target,
                dd30_px=float(dd30_px),
                dd50_px=float(dd50_px),
                dd30_exit=dd30_exit,
                dd30_ts=dd30_ts,
                dd50_exit=dd50_exit,
                dd50_ts=dd50_ts,
                cut_30=cut_30,
                cut_50=cut_50,
                monday_high=mon_high,
                monday_low=mon_low,
                R=R,
                pnl_usd=float(pnl_usd),
                result=result,
                exit_reason=exit_reason,
                trade_num_in_week=primary_count,
                contracts=contracts,
                is_reverse_fade=0,
                is_shifted_primary=0,
                parent_entry_ts="",
            )
        )

        # Parallel reverse fade at flat price (same DD structure); does not block primary
        if use_fade and exit_reason.endswith("flat_at_50") and j + 1 < n:
            fade_side = "short" if side == "long" else "long"
            fade_entry = float(exit_px)
            if fade_side == "long":
                fade_stop = fade_entry - R
                fade_tgt = fade_entry + reward_R * R
            else:
                fade_stop = fade_entry + R
                fade_tgt = fade_entry - reward_R * R
            fpnl, f_exit_ts, f_exit_px, f_reason, _f_end, fmeta = _manage_dd_scale(
                rest,
                j + 1,
                side=fade_side,
                entry=fade_entry,
                stop=fade_stop,
                target=fade_tgt,
                contracts=reverse_fade_units,
                dd_cuts=dd_cuts,
            )
            f_result = _trade_result(f_reason, fpnl)
            f_cut_30, f_cut_50, f_dd30, f_dd50, f_dd30_ts, f_dd50_ts, f_dd30_x, f_dd50_x = (
                _cuts_from_meta(fmeta)
            )

            trades.append(
                Trade(
                    week_monday=mon0.strftime("%Y-%m-%d"),
                    side=fade_side,
                    entry_ts=str(exit_ts),
                    exit_ts=str(f_exit_ts),
                    entry=fade_entry,
                    exit=float(f_exit_px),
                    stop=fade_stop,
                    target=fade_tgt,
                    dd30_px=float(f_dd30),
                    dd50_px=float(f_dd50),
                    dd30_exit=f_dd30_x,
                    dd30_ts=f_dd30_ts,
                    dd50_exit=f_dd50_x,
                    dd50_ts=f_dd50_ts,
                    cut_30=f_cut_30,
                    cut_50=f_cut_50,
                    monday_high=mon_high,
                    monday_low=mon_low,
                    R=R,
                    pnl_usd=float(fpnl),
                    result=f_result,
                    exit_reason="reverse_fade+" + f_reason,
                    trade_num_in_week=primary_count,
                    contracts=reverse_fade_units,
                    is_reverse_fade=1,
                    is_shifted_primary=0,
                    parent_entry_ts=parent_ts,
                )
            )

        # Arm shifted primary: wait for opposite Mon extreme (parallel; does not block)
        if shifted_primary and exit_reason.endswith("flat_at_50") and j + 1 < n:
            pending_shift_side = "short" if side == "long" else "long"
            pending_shift_parent = parent_ts

        i = j + 1
    return trades


def summarize(trades: List[Trade]) -> Dict[str, float]:
    if not trades:
        return {
            "trades": 0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_pnl": 0.0,
            "max_dd": 0.0,
        }
    pnls = np.array([t.pnl_usd for t in trades], dtype=float)
    wins = pnls[pnls > 0].sum()
    losses = pnls[pnls < 0].sum()
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float((eq - peak).min()) if len(eq) else 0.0
    primary = [t for t in trades if not t.is_reverse_fade and not t.is_shifted_primary]
    fades = [t for t in trades if t.is_reverse_fade]
    shifted = [t for t in trades if t.is_shifted_primary]
    return {
        "trades": len(trades),
        "primary_trades": len(primary),
        "reverse_fades": len(fades),
        "shifted_primaries": len(shifted),
        "net_usd": float(pnls.sum()),
        "primary_net_usd": float(sum(t.pnl_usd for t in primary)),
        "fade_net_usd": float(sum(t.pnl_usd for t in fades)),
        "shifted_net_usd": float(sum(t.pnl_usd for t in shifted)),
        "win_rate_pct": 100.0 * float((pnls > 0).mean()),
        "profit_factor": float(wins / abs(losses)) if losses < 0 else (float("inf") if wins > 0 else 0.0),
        "avg_pnl": float(pnls.mean()),
        "max_dd": dd,
        "longs": sum(1 for t in trades if t.side == "long"),
        "shorts": sum(1 for t in trades if t.side == "short"),
        "cut_30": sum(1 for t in primary if t.cut_30),
        "cut_50": sum(1 for t in primary if t.cut_50),
        "flat_at_50_exits": sum(1 for t in primary if t.exit_reason.endswith("flat_at_50")),
        "target_exits": sum(1 for t in primary if t.exit_reason.endswith("target")),
        "week_end_exits": sum(1 for t in primary if t.exit_reason.endswith("week_end")),
        "fade_target": sum(1 for t in fades if t.exit_reason.endswith("target")),
        "fade_stop": sum(1 for t in fades if t.exit_reason.endswith("stop")),
        "fade_flat50": sum(1 for t in fades if t.exit_reason.endswith("flat_at_50")),
        "fade_week_end": sum(1 for t in fades if t.exit_reason.endswith("week_end")),
        "fade_wr_pct": 100.0 * float(np.mean([t.pnl_usd > 0 for t in fades])) if fades else 0.0,
        "shifted_wr_pct": 100.0 * float(np.mean([t.pnl_usd > 0 for t in shifted])) if shifted else 0.0,
        "shifted_target": sum(1 for t in shifted if t.exit_reason.endswith("target")),
        "shifted_flat50": sum(1 for t in shifted if t.exit_reason.endswith("flat_at_50")),
        "shifted_week_end": sum(1 for t in shifted if t.exit_reason.endswith("week_end")),
    }


def write_summary(
    out: Path,
    stats: Dict[str, float],
    trades: List[Trade],
    *,
    reward_R: float,
    contracts: int,
    reverse_fade: bool,
    shifted_primary: bool,
    skip_both_opposed: bool,
) -> None:
    pf = stats["profit_factor"]
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    if shifted_primary:
        sidecar = (
            "- **Shifted primary (parallel):** after flat@50%, wait for opposite Mon extreme "
            "breakout (failed MonH → short MonL; failed MonL → long MonH) with same "
            "3 / DD / 1R–2R; opposite extreme is reserved for the sidecar (does not block "
            "same-side primary re-breaks; does not count toward max primary/week)."
        )
    elif reverse_fade:
        sidecar = (
            "- **Reverse fade (parallel):** after flat@50%, **3** units opposite @ flat price "
            "with same DD cuts; does **not** block the next primary."
        )
    else:
        sidecar = "- Sidecar (fade / shifted): **off**."
    lines = [
        "# EURUSD Monday OR breakout — 15m",
        "",
        "## Rules",
        "",
        "- **Monday OR** / Tue–Fri entries / close beyond high/low.",
        f"- **R** SL=1R TP={reward_R:g}R. **Size:** {contracts} — drop **2**@30% DD, cut **1**@50% DD.",
        (
            "- **HTF filter:** skip when last 1h has **both** MA50/150 and OBV×SMA20 opposed."
            if skip_both_opposed
            else "- HTF filter: **off**."
        ),
        sidecar,
        "- Max **2** primary trades/week. Fee $1.50/unit, PV $100k.",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Trades (all) | {stats['trades']:.0f} |",
        (
            f"| Primary / shifted | {stats.get('primary_trades', 0):.0f} / "
            f"{stats.get('shifted_primaries', 0):.0f} |"
            if shifted_primary
            else (
                f"| Primary / reverse fades | {stats.get('primary_trades', 0):.0f} / "
                f"{stats.get('reverse_fades', 0):.0f} |"
            )
        ),
        f"| Net (all) | ${stats['net_usd']:,.2f} |",
        (
            f"| Primary net / shifted net | ${stats.get('primary_net_usd', 0):,.2f} / "
            f"${stats.get('shifted_net_usd', 0):,.2f} |"
            if shifted_primary
            else (
                f"| Primary net / fade net | ${stats.get('primary_net_usd', 0):,.2f} / "
                f"${stats.get('fade_net_usd', 0):,.2f} |"
            )
        ),
        f"| Win % (all) | {stats['win_rate_pct']:.1f}% |",
        f"| Profit factor | {pf_s} |",
        f"| Avg trade | ${stats['avg_pnl']:,.2f} |",
        f"| Max DD (closed) | ${stats['max_dd']:,.2f} |",
        f"| Primary flat@50% | {stats.get('flat_at_50_exits', 0):.0f} |",
        (
            f"| Shifted WR / tgt / flat50 / week-end | {stats.get('shifted_wr_pct', 0):.1f}% / "
            f"{stats.get('shifted_target', 0):.0f} / {stats.get('shifted_flat50', 0):.0f} / "
            f"{stats.get('shifted_week_end', 0):.0f} |"
            if shifted_primary
            else (
                f"| Fade WR / tgt / flat50 / week-end | {stats.get('fade_wr_pct', 0):.1f}% / "
                f"{stats.get('fade_target', 0):.0f} / {stats.get('fade_flat50', 0):.0f} / "
                f"{stats.get('fade_week_end', 0):.0f} |"
            )
        ),
        "",
    ]
    if trades:
        df = pd.DataFrame([asdict(t) for t in trades])
        df["year"] = pd.to_datetime(df["entry_ts"], utc=True).dt.year
        lines.extend(["## By year (all)", "", "| Year | n | Net | WR |", "|---:|---:|---:|---:|"])
        for y, g in df.groupby("year"):
            wr = 100.0 * (g["pnl_usd"] > 0).mean()
            lines.append(f"| {y} | {len(g)} | ${g['pnl_usd'].sum():,.0f} | {wr:.0f}% |")
        lines.append("")
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-trades-per-week", type=int, default=2)
    parser.add_argument("--reward-R", type=float, default=2.0)
    parser.add_argument("--contracts", type=int, default=CONTRACTS)
    parser.add_argument("--reverse-fade", action="store_true", default=False)
    parser.add_argument("--no-reverse-fade", action="store_false", dest="reverse_fade")
    parser.add_argument("--reverse-fade-units", type=int, default=CONTRACTS)
    parser.add_argument(
        "--shifted-primary",
        action="store_true",
        default=False,
        help="After flat@50%, wait for opposite Mon extreme with same primary structure",
    )
    parser.add_argument(
        "--skip-both-opposed",
        action="store_true",
        default=True,
        help="Skip entries when 1h MA and OBV are both opposed (default on)",
    )
    parser.add_argument(
        "--no-skip-both-opposed",
        action="store_false",
        dest="skip_both_opposed",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.shifted_primary and args.reverse_fade:
        print("Note: --shifted-primary disables reverse fade (mutually exclusive).", flush=True)

    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD 1m → 15m + 1h HTF...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    m1 = concat_all_1m(bars_by_day)
    if m1.index.tz is None:
        m1.index = m1.index.tz_localize(NY)
    else:
        m1.index = m1.index.tz_convert(NY)
    m15 = resample_15m(m1)
    h1 = build_htf_features(m1) if args.skip_both_opposed else None
    print("  %s 15m bars" % f"{len(m15):,}", flush=True)

    out = args.output_root
    tags = []
    if args.shifted_primary:
        tags.append("shiftprim")
    elif args.reverse_fade:
        if args.reverse_fade_units == 1:
            tags.append("revfade_par")
        else:
            tags.append("revfade3_par")
    if args.skip_both_opposed:
        tags.append("htf")
    if tags:
        out = Path(str(out) + "_" + "_".join(tags))
    if abs(args.reward_R - 2.0) > 1e-9:
        out = Path(str(out) + ("_tp%gg" % args.reward_R).replace(".", "p"))

    mondays = list_mondays(m15)
    print(
        "  %d weeks | %d lots | fade=%s | shifted=%s | skip_both_opposed=%s"
        % (
            len(mondays),
            args.contracts,
            args.reverse_fade and not args.shifted_primary,
            args.shifted_primary,
            args.skip_both_opposed,
        ),
        flush=True,
    )
    trades: List[Trade] = []
    for k, mon in enumerate(mondays, start=1):
        trades.extend(
            simulate_week(
                m15,
                mon,
                max_trades=args.max_trades_per_week,
                reward_R=args.reward_R,
                contracts=args.contracts,
                reverse_fade=args.reverse_fade,
                reverse_fade_units=args.reverse_fade_units,
                shifted_primary=args.shifted_primary,
                h1=h1,
                skip_both_opposed=args.skip_both_opposed,
            )
        )
        if k % 200 == 0:
            print("  processed %d/%d weeks (%d trades)" % (k, len(mondays), len(trades)), flush=True)

    out.mkdir(parents=True, exist_ok=True)
    with (out / "trades.csv").open("w", newline="", encoding="utf-8") as fh:
        if trades:
            w = csv.DictWriter(fh, fieldnames=list(asdict(trades[0]).keys()))
            w.writeheader()
            for t in trades:
                w.writerow(asdict(t))
        else:
            fh.write("week_monday\n")

    stats = summarize(trades)
    stats["reward_R"] = args.reward_R
    stats["contracts"] = args.contracts
    stats["reverse_fade"] = bool(args.reverse_fade and not args.shifted_primary)
    stats["shifted_primary"] = args.shifted_primary
    stats["skip_both_opposed"] = args.skip_both_opposed
    (out / "metrics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    write_summary(
        out,
        stats,
        trades,
        reward_R=args.reward_R,
        contracts=args.contracts,
        reverse_fade=bool(args.reverse_fade and not args.shifted_primary),
        shifted_primary=args.shifted_primary,
        skip_both_opposed=args.skip_both_opposed,
    )
    sidecar_net = (
        stats.get("shifted_net_usd", 0)
        if args.shifted_primary
        else stats.get("fade_net_usd", 0)
    )
    print(
        "Trades=%d net=$%.2f primary=$%.2f sidecar=$%.2f WR=%.1f%% PF=%s DD=$%.2f"
        % (
            stats["trades"],
            stats["net_usd"],
            stats.get("primary_net_usd", 0),
            sidecar_net,
            stats["win_rate_pct"],
            ("inf" if stats["profit_factor"] == float("inf") else "%.2f" % stats["profit_factor"]),
            stats["max_dd"],
        ),
        flush=True,
    )
    print("SUMMARY → %s" % (out / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
