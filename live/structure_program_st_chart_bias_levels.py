"""Chart 15m + 1h structure levels after bias changes (no trades).

Walks NQ RTH with dual StructureProgramEngine instances (15m and 1h). For each
15m program/bias flip, records the active structure box + 1h keys and scores
how price interacts with those levels until the next bias change. Charts are
one RTH week of **15m** candles, prioritized for dual-TF confluence with price.

Usage:
  python -m live.structure_program_st_chart_bias_levels --start 2020-01-01 --n 100
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .structure_program_st_study import (
    Structure,
    StructureProgramEngine,
    rth_slice,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st" / "bias_level_charts"
NY = "America/New_York"

# confluence: levels within this many points count as "intersecting"
CONFLUENCE_PTS = 25.0
# how close price must come to a level to count as a touch
TOUCH_PTS = 2.0
H1_LOOKBACK_DAYS = 15
WEEK_SESSIONS = 5  # RTH sessions on chart


@dataclass
class LevelSet:
    program: Optional[str]
    bull_key: Optional[float]
    bear_key: Optional[float]
    # active structure for the program (buy→bull box, sell→bear box)
    bottom: Optional[float] = None
    top: Optional[float] = None
    key: Optional[float] = None
    confirm: Optional[float] = None  # p4
    formed_ts: Optional[pd.Timestamp] = None


@dataclass
class BiasEpisode:
    episode_id: int
    bias_ts: pd.Timestamp
    program: str
    prev_program: Optional[str]
    end_ts: Optional[pd.Timestamp] = None
    m15: LevelSet = field(default_factory=lambda: LevelSet(None, None, None))
    h1: LevelSet = field(default_factory=lambda: LevelSet(None, None, None))
    # interaction counters (filled while walking)
    m15_key_touches: int = 0
    m15_throughs: int = 0
    m15_reclaims: int = 0
    h1_key_touches: int = 0
    h1_throughs: int = 0
    confluence_hits: int = 0  # price touches a 15m∩1h band
    confluence_pairs: int = 0  # how many level-pairs were close at flip
    score: float = 0.0


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


def _struct_box(st: Optional[Structure], kind: str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Return bottom, top, key, confirm for a structure."""
    if st is None:
        return None, None, None, None
    if kind == "bull":
        # LL key = bottom, HH p4 = top
        return float(st.key), float(st.p4), float(st.key), float(st.p4)
    # bear: LL p4 = bottom, HH key = top
    return float(st.p4), float(st.key), float(st.key), float(st.p4)


def snapshot_levels(engine: StructureProgramEngine) -> LevelSet:
    prog = engine.program
    bull = engine.latest("bull")
    bear = engine.latest("bear")
    bull_key = float(bull.key) if bull is not None else None
    bear_key = float(bear.key) if bear is not None else None
    bottom = top = key = confirm = formed = None
    if prog == "buy" and bull is not None:
        bottom, top, key, confirm = _struct_box(bull, "bull")
        formed = bull.formed_ts
    elif prog == "sell" and bear is not None:
        bottom, top, key, confirm = _struct_box(bear, "bear")
        formed = bear.formed_ts
    return LevelSet(
        program=prog,
        bull_key=bull_key,
        bear_key=bear_key,
        bottom=bottom,
        top=top,
        key=key,
        confirm=confirm,
        formed_ts=formed,
    )


def _near(a: Optional[float], b: Optional[float], tol: float) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def confluence_pairs(m15: LevelSet, h1: LevelSet, tol: float = CONFLUENCE_PTS) -> List[Tuple[str, float, float]]:
    """Pairs of (label, m15_px, h1_px) within tol."""
    pairs: List[Tuple[str, float, float]] = []
    m15_lvls = [
        ("m15_key", m15.key),
        ("m15_bottom", m15.bottom),
        ("m15_top", m15.top),
        ("m15_bull", m15.bull_key),
        ("m15_bear", m15.bear_key),
    ]
    h1_lvls = [
        ("h1_key", h1.key),
        ("h1_bottom", h1.bottom),
        ("h1_top", h1.top),
        ("h1_bull", h1.bull_key),
        ("h1_bear", h1.bear_key),
    ]
    seen = set()
    for lm, vm in m15_lvls:
        if vm is None:
            continue
        for lh, vh in h1_lvls:
            if vh is None:
                continue
            if abs(float(vm) - float(vh)) <= tol:
                mid = round(0.5 * (float(vm) + float(vh)), 2)
                if mid in seen:
                    continue
                seen.add(mid)
                pairs.append(("%s∩%s" % (lm, lh), float(vm), float(vh)))
    return pairs


def _touched(lo: float, hi: float, level: float, pad: float = TOUCH_PTS) -> bool:
    return (lo - pad) <= level <= (hi + pad)


def _update_interactions(ep: BiasEpisode, bar: pd.Series, through_state: Dict[str, bool]) -> None:
    """Accumulate touch / through / reclaim / confluence stats on a 15m bar."""
    lo, hi, cl = float(bar["low"]), float(bar["high"]), float(bar["close"])
    prog = ep.program
    m15, h1 = ep.m15, ep.h1

    if m15.key is not None and _touched(lo, hi, float(m15.key)):
        ep.m15_key_touches += 1
    if h1.key is not None and _touched(lo, hi, float(h1.key)):
        ep.h1_key_touches += 1

    # through / reclaim vs program key (buy: through below LL; sell: through above HH)
    if m15.key is not None:
        k = float(m15.key)
        if prog == "buy":
            if lo < k:
                if not through_state.get("m15"):
                    ep.m15_throughs += 1
                    through_state["m15"] = True
            elif through_state.get("m15") and cl > k:
                ep.m15_reclaims += 1
                through_state["m15"] = False
        elif prog == "sell":
            if hi > k:
                if not through_state.get("m15"):
                    ep.m15_throughs += 1
                    through_state["m15"] = True
            elif through_state.get("m15") and cl < k:
                ep.m15_reclaims += 1
                through_state["m15"] = False

    if h1.key is not None:
        k = float(h1.key)
        if prog == "buy":
            if lo < k and not through_state.get("h1"):
                ep.h1_throughs += 1
                through_state["h1"] = True
            elif through_state.get("h1") and cl > k:
                through_state["h1"] = False
        elif prog == "sell":
            if hi > k and not through_state.get("h1"):
                ep.h1_throughs += 1
                through_state["h1"] = True
            elif through_state.get("h1") and cl < k:
                through_state["h1"] = False

    for _lab, vm, vh in confluence_pairs(m15, h1):
        band_lo, band_hi = min(vm, vh), max(vm, vh)
        # widen slightly
        if hi >= band_lo - TOUCH_PTS and lo <= band_hi + TOUCH_PTS:
            ep.confluence_hits += 1
            break


def score_episode(ep: BiasEpisode) -> float:
    """Prioritize dual-TF confluence interacting with price."""
    return (
        10.0 * ep.confluence_hits
        + 6.0 * ep.confluence_pairs
        + 2.0 * ep.m15_key_touches
        + 2.0 * ep.h1_key_touches
        + 3.0 * ep.m15_throughs
        + 3.0 * ep.h1_throughs
        + 4.0 * ep.m15_reclaims
    )


def _ingest_h1_day(
    engine: StructureProgramEngine,
    day_1h: pd.DataFrame,
    lookback: Sequence[pd.DataFrame],
) -> List[Structure]:
    """Ingest one day of 1h bars with lookback so swings can confirm across days."""
    frames = [b for b in lookback if b is not None and not b.empty] + (
        [day_1h] if day_1h is not None and not day_1h.empty else []
    )
    if not frames:
        return []
    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    # Only apply engine walk on the new day's timestamps
    if day_1h is None or day_1h.empty:
        return []
    day_start = day_1h.index[0]
    # Rebuild swing confirms on combined, but feed engine only from day_start
    # by slicing combined and using a temp walk for the day portion with
    # pre-seeded swings already in engine from prior days.
    # Practical approach: confirm_swings on combined; process bars >= day_start
    from .structure_program_st_study import confirm_swings, try_form_structures

    day_swings = confirm_swings(combined)
    by_confirm: Dict[pd.Timestamp, list] = {}
    for sw in day_swings:
        if sw[0] < day_start:
            continue
        by_confirm.setdefault(sw[0], []).append(sw)

    new_structs: List[Structure] = []
    for ts, row in day_1h.iterrows():
        for sw in by_confirm.get(ts, []):
            if engine.swings and engine.swings[-1][1] == sw[1]:
                prev = engine.swings[-1]
                if sw[1] == "H" and sw[2] >= prev[2]:
                    engine.swings[-1] = sw
                elif sw[1] == "L" and sw[2] <= prev[2]:
                    engine.swings[-1] = sw
                else:
                    continue
            else:
                engine.swings.append(sw)
            for st in try_form_structures(engine.swings):
                sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                if sig in engine._seen_structure_keys:
                    continue
                engine._seen_structure_keys.add(sig)
                if st.kind == "bull":
                    engine.bull.append(st)
                else:
                    engine.bear.append(st)
                new_structs.append(st)
        engine._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
    return new_structs


def collect_episodes(
    gby: Dict[date, pd.DataFrame],
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> Tuple[List[BiasEpisode], Dict[date, pd.DataFrame]]:
    """Walk dual engines; return bias episodes + per-day 15m frames for charting."""
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    eng15 = StructureProgramEngine()
    eng1h = StructureProgramEngine()
    h1_buf: List[pd.DataFrame] = []
    bars15_by_day: Dict[date, pd.DataFrame] = {}

    episodes: List[BiasEpisode] = []
    active: Optional[BiasEpisode] = None
    through_state: Dict[str, bool] = {}
    prev_prog: Optional[str] = None
    eid = 0

    print("Walking dual structure engines over %d days…" % len(days), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b15 = to_15m(rth)
        b1h = to_1h(rth)
        bars15_by_day[d] = b15

        # 15m: standard day ingest, but we need intra-day bias flips
        # Re-implement bar walk to catch program changes mid-day
        from .structure_program_st_study import confirm_swings, try_form_structures

        day_swings = confirm_swings(b15)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            by_confirm.setdefault(sw[0], []).append(sw)

        for ts, row in b15.iterrows():
            for sw in by_confirm.get(ts, []):
                if eng15.swings and eng15.swings[-1][1] == sw[1]:
                    prev = eng15.swings[-1]
                    if sw[1] == "H" and sw[2] >= prev[2]:
                        eng15.swings[-1] = sw
                    elif sw[1] == "L" and sw[2] <= prev[2]:
                        eng15.swings[-1] = sw
                    else:
                        continue
                else:
                    eng15.swings.append(sw)
                for st in try_form_structures(eng15.swings):
                    sig = (st.kind, round(st.key, 4), round(st.p4, 4), str(st.formed_ts))
                    if sig in eng15._seen_structure_keys:
                        continue
                    eng15._seen_structure_keys.add(sig)
                    if st.kind == "bull":
                        eng15.bull.append(st)
                    else:
                        eng15.bear.append(st)
            eng15._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))

            prog = eng15.program
            if prog in {"buy", "sell"} and prog != prev_prog and eng15.ready:
                # close previous
                if active is not None:
                    active.end_ts = ts
                    active.score = score_episode(active)
                    episodes.append(active)
                eid += 1
                m15 = snapshot_levels(eng15)
                h1 = snapshot_levels(eng1h)
                pairs = confluence_pairs(m15, h1)
                active = BiasEpisode(
                    episode_id=eid,
                    bias_ts=ts,
                    program=prog,
                    prev_program=prev_prog,
                    m15=m15,
                    h1=h1,
                    confluence_pairs=len(pairs),
                )
                through_state = {}
                prev_prog = prog

            if active is not None and prog == active.program:
                _update_interactions(active, row, through_state)

        # 1h ingest after 15m day (levels for *next* bars; still useful mid-sample)
        _ingest_h1_day(eng1h, b1h, h1_buf[-H1_LOOKBACK_DAYS:])
        if not b1h.empty:
            h1_buf.append(b1h)
            h1_buf = h1_buf[-H1_LOOKBACK_DAYS:]

        if di % 250 == 0:
            print(
                "  %d/%d days | episodes %d | prog15=%s prog1h=%s"
                % (di, len(days), len(episodes), eng15.program, eng1h.program),
                flush=True,
            )

    if active is not None:
        # close at last bar
        last_day = max(bars15_by_day)
        last_ts = bars15_by_day[last_day].index[-1]
        active.end_ts = last_ts
        active.score = score_episode(active)
        episodes.append(active)

    print("Collected %d bias episodes" % len(episodes), flush=True)
    return episodes, bars15_by_day


def week_sessions(all_days: List[date], anchor: date, n: int = WEEK_SESSIONS) -> List[date]:
    """n RTH sessions starting at the session containing anchor (or next available)."""
    if not all_days:
        return []
    # start at first session >= anchor, else nearest prior
    start_candidates = [d for d in all_days if d >= anchor]
    if not start_candidates:
        return all_days[-n:]
    i0 = all_days.index(start_candidates[0])
    # prefer centering: 1 session before + rest after when possible
    i_start = max(0, i0 - 1)
    chunk = all_days[i_start : i_start + n]
    if len(chunk) < n and i_start > 0:
        i_start = max(0, len(all_days) - n)
        chunk = all_days[i_start : i_start + n]
    return chunk


def select_episodes(episodes: List[BiasEpisode], n: int) -> List[BiasEpisode]:
    """Top-n by score; prefer dual-TF confluence, then light time diversification."""
    # Drop empty interactions unless we truly need fill
    rich = [e for e in episodes if e.score > 0 and (e.confluence_hits > 0 or e.confluence_pairs > 0)]
    mid = [e for e in episodes if e.score > 0 and e not in rich]
    pool = rich if len(rich) >= n else rich + sorted(mid, key=lambda e: e.score, reverse=True)
    if len(pool) < n:
        pool = pool + sorted(
            [e for e in episodes if e not in pool], key=lambda e: e.score, reverse=True
        )
    ranked = sorted(pool, key=lambda e: (e.confluence_hits, e.score), reverse=True)
    if len(ranked) <= n:
        return sorted(ranked, key=lambda e: e.bias_ts)
    n_top = int(n * 0.75)
    chosen = ranked[:n_top]
    rest = ranked[n_top:]
    rest_time = sorted(rest, key=lambda e: e.bias_ts)
    need = n - len(chosen)
    if need > 0 and rest_time:
        step = max(1, len(rest_time) // need)
        extra = rest_time[::step][:need]
        if len(extra) < need:
            have = {e.episode_id for e in chosen + extra}
            for e in rest:
                if e.episode_id not in have:
                    extra.append(e)
                if len(extra) >= need:
                    break
        chosen.extend(extra[:need])
    return sorted(chosen, key=lambda e: e.bias_ts)[:n]


def plot_episode(
    ep: BiasEpisode,
    bars15_by_day: Dict[date, pd.DataFrame],
    out_path: Path,
    chart_id: int,
) -> bool:
    all_days = sorted(bars15_by_day)
    anchor = ep.bias_ts.tz_convert(NY).date() if ep.bias_ts.tzinfo else ep.bias_ts.date()
    sessions = week_sessions(all_days, anchor, WEEK_SESSIONS)
    if len(sessions) < 3:
        return False
    frames = [bars15_by_day[d] for d in sessions if d in bars15_by_day and not bars15_by_day[d].empty]
    if not frames:
        return False
    plot = pd.concat(frames).sort_index()
    plot = plot[~plot.index.duplicated(keep="last")]
    if len(plot) < 20:
        return False

    fig, ax = plt.subplots(figsize=(18, 9))
    x = np.arange(len(plot))
    o = plot["open"].to_numpy()
    h = plot["high"].to_numpy()
    l = plot["low"].to_numpy()
    c = plot["close"].to_numpy()
    up = c >= o
    ax.vlines(x, l, h, color="#888", lw=0.7, zorder=1)
    ax.vlines(x[up], o[up], c[up], color="#1a9850", lw=2.0, zorder=2)
    ax.vlines(x[~up], c[~up], o[~up], color="#d73027", lw=2.0, zorder=2)

    def _xi(ts: pd.Timestamp) -> Optional[int]:
        ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize(NY)
        else:
            ts = ts.tz_convert(NY)
        idx = plot.index
        for i, bt in enumerate(idx):
            if bt <= ts < bt + pd.Timedelta(minutes=15):
                return i
        deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(idx)]
        return min(deltas)[1] if deltas else None

    # bias window shading
    bi = _xi(ep.bias_ts)
    ei = _xi(ep.end_ts) if ep.end_ts is not None else None
    if bi is not None:
        ax.axvline(bi, color="#212121", lw=1.6, ls="-", zorder=4, label="Bias → %s" % ep.program)
        end_i = ei if ei is not None else len(plot) - 1
        end_i = max(bi, min(end_i, len(plot) - 1))
        shade = "#bbdefb" if ep.program == "buy" else "#f8bbd0"
        ax.axvspan(bi, end_i, color=shade, alpha=0.15, zorder=0, label="Bias episode")

    m15, h1 = ep.m15, ep.h1

    # 15m structure box
    if m15.bottom is not None and m15.top is not None:
        ax.axhspan(
            float(m15.bottom),
            float(m15.top),
            color="#90caf9" if ep.program == "buy" else "#ce93d8",
            alpha=0.12,
            zorder=0,
            label="15m structure box",
        )
    if m15.key is not None:
        ax.axhline(
            float(m15.key),
            color="#0d47a1",
            lw=2.0,
            ls="-",
            zorder=5,
            label="15m key (SL) %.1f" % float(m15.key),
        )
    if m15.confirm is not None and m15.confirm != m15.key:
        ax.axhline(
            float(m15.confirm),
            color="#1565c0",
            lw=1.3,
            ls="--",
            zorder=5,
            label="15m confirm %.1f" % float(m15.confirm),
        )
    if m15.bull_key is not None and m15.bull_key != m15.key:
        ax.axhline(float(m15.bull_key), color="#1976d2", lw=0.8, ls=":", alpha=0.55, label="15m bull LL")
    if m15.bear_key is not None and m15.bear_key != m15.key:
        ax.axhline(float(m15.bear_key), color="#7b1fa2", lw=0.8, ls=":", alpha=0.55, label="15m bear HH")

    # 1h levels (thicker / distinct)
    if h1.key is not None:
        ax.axhline(
            float(h1.key),
            color="#e65100",
            lw=2.2,
            ls="-",
            zorder=6,
            label="1h key %.1f" % float(h1.key),
        )
    if h1.bottom is not None and h1.bottom != h1.key:
        ax.axhline(
            float(h1.bottom),
            color="#ef6c00",
            lw=1.4,
            ls="--",
            zorder=6,
            label="1h bottom %.1f" % float(h1.bottom),
        )
    if h1.top is not None and h1.top != h1.key:
        ax.axhline(
            float(h1.top),
            color="#ef6c00",
            lw=1.4,
            ls="--",
            zorder=6,
            label="1h top %.1f" % float(h1.top),
        )
    if h1.bull_key is not None and h1.bull_key not in {h1.key, h1.bottom, h1.top}:
        ax.axhline(float(h1.bull_key), color="#ff8f00", lw=0.9, ls=":", alpha=0.7, label="1h bull LL")
    if h1.bear_key is not None and h1.bear_key not in {h1.key, h1.bottom, h1.top}:
        ax.axhline(float(h1.bear_key), color="#6d4c41", lw=0.9, ls=":", alpha=0.7, label="1h bear HH")

    # confluence bands
    pairs = confluence_pairs(m15, h1)
    for i, (lab, vm, vh) in enumerate(pairs[:4]):
        lo_b, hi_b = min(vm, vh), max(vm, vh)
        ax.axhspan(
            lo_b,
            hi_b if hi_b > lo_b else lo_b + 0.5,
            color="#ffeb3b",
            alpha=0.22,
            zorder=1,
            label="15m∩1h confluence" if i == 0 else None,
        )

    # session separators
    for d in sessions[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bdbdbd", lw=0.8, ls="--", zorder=0)
                break

    y_lo = float(np.nanmin(l))
    y_hi = float(np.nanmax(h))
    pad = 0.02 * (y_hi - y_lo + 1e-9)
    # keep levels in view when possible
    for lvl in [m15.key, m15.bottom, m15.top, h1.key, h1.bottom, h1.top]:
        if lvl is None:
            continue
        y_lo = min(y_lo, float(lvl) - pad)
        y_hi = max(y_hi, float(lvl) + pad)
    ax.set_ylim(y_lo - pad, y_hi + pad)

    bias_s = ep.bias_ts.tz_convert(NY).strftime("%Y-%m-%d %H:%M") if ep.bias_ts.tzinfo else str(ep.bias_ts)
    ax.set_title(
        "NQ 15m | bias→%s @ %s (from %s) | score=%.0f | "
        "m15 touches/thru/reclaim=%d/%d/%d · h1 touches/thru=%d/%d · confluence hits=%d pairs=%d"
        % (
            ep.program,
            bias_s,
            ep.prev_program or "none",
            ep.score,
            ep.m15_key_touches,
            ep.m15_throughs,
            ep.m15_reclaims,
            ep.h1_key_touches,
            ep.h1_throughs,
            ep.confluence_hits,
            ep.confluence_pairs,
        ),
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    ax.set_xlim(-1, len(plot))
    step = max(1, len(plot) // 16)
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


def _write_readme(out: Path, selected: List[BiasEpisode], n_total: int) -> None:
    lines = [
        "# Structure bias-level charts (15m + 1h)",
        "",
        "No trades — visual review of how price interacts with structure levels",
        "after a **15m program/bias change**, until the next bias change.",
        "",
        "## What's on each chart",
        "",
        "- **Candles:** ~1 RTH week (5 sessions) of **15-minute** bars",
        "- **Black vertical:** 15m bias flip (buy/sell program)",
        "- **Shaded span:** bias episode (until next flip or week end)",
        "- **Blue band / lines:** 15m active structure box + key (SL) + confirm",
        "- **Orange lines:** 1h structure key / box / bull·bear keys",
        "- **Yellow band:** 15m∩1h confluence (levels within %.0f pts)" % CONFLUENCE_PTS,
        "",
        "## Selection",
        "",
        "Scored for dual-TF interaction (confluence hits weighted highest), then",
        "time-diversified. **%d / %d** episodes charted." % (len(selected), n_total),
        "",
        "## Legend scores (title)",
        "",
        "| token | meaning |",
        "|---|---|",
        "| m15 touches/thru/reclaim | 15m key interactions in episode |",
        "| h1 touches/thru | 1h key interactions |",
        "| confluence hits/pairs | price in 15m∩1h band / close level-pairs at flip |",
        "",
        "## Files",
        "",
        "- `charts/` — PNGs ranked by chart id (time order of selected set)",
        "- `episodes.csv` — full scored episode table",
        "- `charted.csv` — the selected subset",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    out = Path(args.out)
    chart_dir = out / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    for old in chart_dir.glob("*.png"):
        old.unlink()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    episodes, bars15 = collect_episodes(gby, start=start, end=end)
    if not episodes:
        print("No bias episodes found.")
        return

    # persist full table
    rows = []
    for e in episodes:
        rows.append(
            {
                "episode_id": e.episode_id,
                "bias_ts": e.bias_ts,
                "end_ts": e.end_ts,
                "program": e.program,
                "prev_program": e.prev_program,
                "m15_key": e.m15.key,
                "m15_bottom": e.m15.bottom,
                "m15_top": e.m15.top,
                "h1_key": e.h1.key,
                "h1_bottom": e.h1.bottom,
                "h1_top": e.h1.top,
                "m15_key_touches": e.m15_key_touches,
                "m15_throughs": e.m15_throughs,
                "m15_reclaims": e.m15_reclaims,
                "h1_key_touches": e.h1_key_touches,
                "h1_throughs": e.h1_throughs,
                "confluence_hits": e.confluence_hits,
                "confluence_pairs": e.confluence_pairs,
                "score": e.score,
            }
        )
    df = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "episodes.csv", index=False)

    selected = select_episodes(episodes, args.n)
    print("Charting %d episodes…" % len(selected), flush=True)
    by_id = {e.episode_id: r for e, r in zip(episodes, rows)}
    charted = []
    for i, ep in enumerate(selected, 1):
        bias_d = ep.bias_ts.tz_convert(NY).strftime("%Y-%m-%d") if ep.bias_ts.tzinfo else str(ep.bias_ts)[:10]
        fname = "%03d_%s_%s_score%.0f.png" % (i, bias_d, ep.program, ep.score)
        path = chart_dir / fname
        ok = plot_episode(ep, bars15, path, i)
        if ok:
            row = dict(by_id[ep.episode_id])
            row["chart_id"] = i
            row["file"] = fname
            charted.append(row)
            if i % 10 == 0:
                print("  wrote %d/%d" % (i, len(selected)), flush=True)
        else:
            print("  skip episode %d (insufficient bars)" % ep.episode_id, flush=True)

    pd.DataFrame(charted).to_csv(out / "charted.csv", index=False)

    # INDEX
    idx_lines = ["# Bias-level charts", "", "| # | file | bias | program | score | conf_hits |", "|--:|---|---|---|---:|---:|"]
    for r in charted:
        idx_lines.append(
            "| %d | `%s` | %s | %s | %.0f | %d |"
            % (r["chart_id"], r["file"], str(r["bias_ts"])[:16], r["program"], r["score"], r["confluence_hits"])
        )
    (chart_dir / "INDEX.md").write_text("\n".join(idx_lines) + "\n")
    _write_readme(out, selected, len(episodes))
    print("Wrote %d charts → %s" % (len(charted), out), flush=True)


if __name__ == "__main__":
    main()
