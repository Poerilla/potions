"""Two bias-review chart packs (no trades).

1) **1h pack** — week of 1-hour candles; buy/sell shade; bias-candle high/low
   projected as a range until the next bias change
2) **15m pack** — week of 15-minute candles; vertical line at each bias flip +
   horizontal structure-key line that persists until the next flip

Bias = 15m StructureProgramEngine program (buy/sell). 150 charts each by default;
same week anchors so packs line up by chart id.

Usage:
  python -m live.structure_program_st_chart_bias_weeks --start 2020-01-01 --n 150
  python -m live.structure_program_st_chart_bias_weeks --pack 1h --n 150
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from .structure_program_st_study import (
    StructureProgramEngine,
    confirm_swings,
    rth_slice,
    to_15m,
    try_form_structures,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "live" / "state" / "structure_program_st"
OUT_1H = OUT_ROOT / "bias_weeks_1h"
OUT_15M = OUT_ROOT / "bias_weeks_15m"
NY = "America/New_York"
WEEK_SESSIONS = 5
MONTH_SESSIONS = 21  # ~1 RTH month of sessions on 1h charts

BUY_SHADE = "#bbdefb"
SELL_SHADE = "#f8bbd0"
BUY_KEY = "#0d47a1"
SELL_KEY = "#880e4f"
BIAS_VLINE = "#212121"


@dataclass
class BiasFlip:
    flip_id: int
    ts: pd.Timestamp
    program: str  # buy | sell
    prev_program: Optional[str]
    key: Optional[float]  # active structure key at flip
    bottom: Optional[float] = None
    top: Optional[float] = None


@dataclass
class WeekAnchor:
    chart_id: int
    anchor_date: date
    sessions: List[date]
    flips: List[BiasFlip]  # flips intersecting the week window
    n_flips: int
    primary_flip_id: int


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


def _active_levels(engine: StructureProgramEngine) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    prog = engine.program
    if prog == "buy":
        st = engine.latest("bull")
        if st is None:
            return None, None, None
        return float(st.key), float(st.key), float(st.p4)  # key, bottom, top
    if prog == "sell":
        st = engine.latest("bear")
        if st is None:
            return None, None, None
        return float(st.key), float(st.p4), float(st.key)
    return None, None, None


def collect_flips(
    gby: Dict[date, pd.DataFrame],
    start: Optional[date],
    end: Optional[date],
) -> Tuple[List[BiasFlip], Dict[date, pd.DataFrame], Dict[date, pd.DataFrame]]:
    """Walk 15m engine; return flips + per-day 15m/1h bars."""
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    eng = StructureProgramEngine()
    flips: List[BiasFlip] = []
    bars15: Dict[date, pd.DataFrame] = {}
    bars1h: Dict[date, pd.DataFrame] = {}
    prev_prog: Optional[str] = None
    fid = 0

    print("Walking 15m structure engine over %d days…" % len(days), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b15 = to_15m(rth)
        b1h = to_1h(rth)
        bars15[d] = b15
        bars1h[d] = b1h

        day_swings = confirm_swings(b15)
        by_confirm: Dict[pd.Timestamp, list] = {}
        for sw in day_swings:
            by_confirm.setdefault(sw[0], []).append(sw)

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
            eng._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))

            prog = eng.program
            if prog in {"buy", "sell"} and prog != prev_prog and eng.ready:
                fid += 1
                key, bottom, top = _active_levels(eng)
                flips.append(
                    BiasFlip(
                        flip_id=fid,
                        ts=ts,
                        program=prog,
                        prev_program=prev_prog,
                        key=key,
                        bottom=bottom,
                        top=top,
                    )
                )
                prev_prog = prog

        if di % 250 == 0:
            print("  %d/%d days | flips %d | prog=%s" % (di, len(days), len(flips), eng.program), flush=True)

    print("Collected %d bias flips" % len(flips), flush=True)
    return flips, bars15, bars1h


def session_window(all_days: List[date], anchor: date, n: int) -> List[date]:
    """n RTH sessions starting near anchor (1 session of pre-context when possible)."""
    if not all_days:
        return []
    ge = [d for d in all_days if d >= anchor]
    if not ge:
        return all_days[-n:]
    i0 = all_days.index(ge[0])
    i_start = max(0, i0 - 1)
    chunk = all_days[i_start : i_start + n]
    if len(chunk) < n:
        i_start = max(0, len(all_days) - n)
        chunk = all_days[i_start : i_start + n]
    return chunk


def week_sessions(all_days: List[date], anchor: date, n: int = WEEK_SESSIONS) -> List[date]:
    return session_window(all_days, anchor, n)


def _ny_date(ts: pd.Timestamp) -> date:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.date()


def select_week_anchors(
    flips: List[BiasFlip],
    all_days: List[date],
    n: int,
    sessions_per_chart: int = WEEK_SESSIONS,
) -> List[WeekAnchor]:
    """Time-stratified windows anchored on flips (one chart per selected flip)."""
    if not flips:
        return []
    min_sessions = min(3, sessions_per_chart)
    # Prefer unique window-starts first; if short of n, allow overlapping windows
    by_start: Dict[date, Tuple[List[date], List[BiasFlip], int]] = {}
    per_flip: List[Tuple[date, List[date], List[BiasFlip], int]] = []
    for fl in flips:
        sessions = session_window(all_days, _ny_date(fl.ts), sessions_per_chart)
        if len(sessions) < min_sessions:
            continue
        start, end = sessions[0], sessions[-1]
        week_flips = [f for f in flips if start <= _ny_date(f.ts) <= end]
        per_flip.append((start, sessions, week_flips, fl.flip_id))
        if start not in by_start:
            by_start[start] = (sessions, week_flips, fl.flip_id)

    unique = sorted(
        [(s, v[0], v[1], v[2]) for s, v in by_start.items()], key=lambda c: c[0]
    )
    if len(unique) >= n:
        candidates = unique
    else:
        # fill with remaining flip-anchored weeks (may overlap)
        have = {c[3] for c in unique}
        extra = [c for c in per_flip if c[3] not in have]
        extra.sort(key=lambda c: c[0])
        candidates = unique + extra

    if not candidates:
        return []

    if len(candidates) <= n:
        picked = candidates
    else:
        step = max(1e-9, len(candidates) / float(n))
        idxs = sorted({min(len(candidates) - 1, int(i * step)) for i in range(n)})
        while len(idxs) < n:
            for j in range(len(candidates)):
                if j not in idxs:
                    idxs.append(j)
                if len(idxs) >= n:
                    break
        idxs = sorted(idxs)[:n]
        picked = [candidates[i] for i in idxs]

    anchors: List[WeekAnchor] = []
    for i, (start, sessions, week_flips, primary) in enumerate(picked, 1):
        anchors.append(
            WeekAnchor(
                chart_id=i,
                anchor_date=start,
                sessions=sessions,
                flips=week_flips,
                n_flips=len(week_flips),
                primary_flip_id=primary,
            )
        )
    return anchors


def _concat_days(by_day: Dict[date, pd.DataFrame], sessions: List[date]) -> pd.DataFrame:
    frames = [by_day[d] for d in sessions if d in by_day and not by_day[d].empty]
    if not frames:
        return pd.DataFrame()
    plot = pd.concat(frames).sort_index()
    return plot[~plot.index.duplicated(keep="last")]


def _xi(plot: pd.DataFrame, ts: pd.Timestamp, bar_minutes: int) -> Optional[int]:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    idx = plot.index
    delta = pd.Timedelta(minutes=bar_minutes)
    for i, bt in enumerate(idx):
        if bt <= ts < bt + delta:
            return i
    if not len(idx):
        return None
    deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(idx)]
    return min(deltas)[1]


def _program_spans(
    flips: List[BiasFlip],
    plot: pd.DataFrame,
    all_flips: List[BiasFlip],
    bar_minutes: int,
) -> List[Tuple[int, int, str]]:
    """Return (i0, i1, program) spans covering the plot window."""
    if plot.empty:
        return []
    t0, t1 = plot.index[0], plot.index[-1]
    # find program in force at window start
    prior = [f for f in all_flips if f.ts <= t0]
    spans: List[Tuple[int, int, str]] = []
    if prior:
        cur_prog = prior[-1].program
        cur_i = 0
    else:
        # wait for first flip in/after window
        cur_prog = None
        cur_i = 0

    in_window = [f for f in all_flips if t0 <= f.ts <= t1]
    for fl in in_window:
        xi = _xi(plot, fl.ts, bar_minutes)
        if xi is None:
            continue
        if cur_prog is not None and xi > cur_i:
            spans.append((cur_i, xi, cur_prog))
        cur_prog = fl.program
        cur_i = xi
    if cur_prog is not None:
        spans.append((cur_i, len(plot) - 1, cur_prog))
    return spans


def _draw_candles(ax, plot: pd.DataFrame) -> np.ndarray:
    x = np.arange(len(plot))
    o = plot["open"].to_numpy()
    h = plot["high"].to_numpy()
    l = plot["low"].to_numpy()
    c = plot["close"].to_numpy()
    up = c >= o
    ax.vlines(x, l, h, color="#888", lw=0.8, zorder=2)
    ax.vlines(x[up], o[up], c[up], color="#1a9850", lw=2.2, zorder=3)
    ax.vlines(x[~up], c[~up], o[~up], color="#d73027", lw=2.2, zorder=3)
    return x


def _session_seps(ax, plot: pd.DataFrame, sessions: List[date]) -> None:
    for d in sessions[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bdbdbd", lw=0.8, ls="--", zorder=1)
                break


def _bias_candle_1h(
    bars1h: Dict[date, pd.DataFrame],
    flip_ts: pd.Timestamp,
) -> Optional[Tuple[float, float, pd.Timestamp]]:
    """Return (high, low, bar_ts) for the 1h candle containing the bias flip."""
    ts = pd.Timestamp(flip_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    d = ts.date()
    day = bars1h.get(d)
    if day is None or day.empty:
        # nearest session day
        for dd in sorted(bars1h):
            if abs((dd - d).days) <= 1 and not bars1h[dd].empty:
                day = bars1h[dd]
                break
    if day is None or day.empty:
        return None
    # bar label left/closed-left: find bar where bt <= ts < bt+1h
    for bt, row in day.iterrows():
        if bt <= ts < bt + pd.Timedelta(hours=1):
            return float(row["high"]), float(row["low"]), bt
    # fallback nearest
    deltas = [(abs((bt - ts).total_seconds()), bt, row) for bt, row in day.iterrows()]
    if not deltas:
        return None
    _, bt, row = min(deltas, key=lambda t: t[0])
    return float(row["high"]), float(row["low"]), bt


def plot_1h_week(
    anchor: WeekAnchor,
    bars1h: Dict[date, pd.DataFrame],
    all_flips: List[BiasFlip],
    out_path: Path,
) -> bool:
    plot = _concat_days(bars1h, anchor.sessions)
    if len(plot) < 8:
        return False

    fig, ax = plt.subplots(figsize=(22, 9))
    x = _draw_candles(ax, plot)

    # shade buy/sell bias backgrounds
    spans = _program_spans(anchor.flips, plot, all_flips, bar_minutes=60)
    labeled = set()
    for i0, i1, prog in spans:
        color = BUY_SHADE if prog == "buy" else SELL_SHADE
        lab = "bias buy" if prog == "buy" else "bias sell"
        ax.axvspan(
            i0,
            max(i1, i0 + 0.5),
            color=color,
            alpha=0.22,
            zorder=0,
            label=lab if lab not in labeled else None,
        )
        labeled.add(lab)

    t0, t1 = plot.index[0], plot.index[-1]
    # flips that define ranges intersecting this week (carry prior + in-window)
    prior = [f for f in all_flips if f.ts < t0]
    relevant = ([prior[-1]] if prior else []) + [f for f in all_flips if t0 <= f.ts <= t1]

    labeled_range = False
    labeled_v = False
    for i, fl in enumerate(relevant):
        end_ts = relevant[i + 1].ts if i + 1 < len(relevant) else t1
        candle = _bias_candle_1h(bars1h, fl.ts)
        if candle is None:
            continue
        hi, lo, bar_ts = candle

        # horizontal span: from bias candle (or week start if prior) → next flip / week end
        if fl.ts < t0:
            i0 = 0
        else:
            i0 = _xi(plot, bar_ts, 60)
            if i0 is None:
                i0 = _xi(plot, fl.ts, 60)
        i1 = _xi(plot, end_ts, 60)
        if i1 is None:
            i1 = len(plot) - 1
        if i0 is None:
            continue
        i1 = max(i1, i0 + 1)

        color = BUY_KEY if fl.program == "buy" else SELL_KEY
        ax.hlines(
            hi,
            xmin=i0,
            xmax=i1,
            colors=color,
            lw=1.8,
            zorder=6,
            label="bias-candle H/L range" if not labeled_range else None,
        )
        ax.hlines(lo, xmin=i0, xmax=i1, colors=color, lw=1.8, zorder=6)
        # light fill between H/L for the projected range
        ax.fill_between(
            [i0, i1],
            [lo, lo],
            [hi, hi],
            color=color,
            alpha=0.08,
            zorder=1,
        )
        labeled_range = True
        ax.text(
            i0 + 0.3,
            hi,
            " %s H %.0f" % (fl.program, hi),
            color=color,
            fontsize=7,
            va="bottom",
            zorder=7,
        )
        ax.text(
            i0 + 0.3,
            lo,
            " %s L %.0f" % (fl.program, lo),
            color=color,
            fontsize=7,
            va="top",
            zorder=7,
        )

        if fl.ts >= t0:
            xi = _xi(plot, fl.ts, 60)
            if xi is not None:
                ax.axvline(
                    xi,
                    color=BIAS_VLINE,
                    lw=1.4,
                    ls="-",
                    alpha=0.85,
                    zorder=5,
                    label="bias change" if not labeled_v else None,
                )
                labeled_v = True
                # mark the bias candle
                ax.scatter(
                    [xi],
                    [(hi + lo) / 2.0],
                    marker="o",
                    s=40,
                    color=color,
                    edgecolors="white",
                    zorder=8,
                )

    _session_seps(ax, plot, anchor.sessions)

    ax.set_title(
        "NQ 1h | %s → %s (~1mo) | %d bias flip(s) | shade=bias · H/L of bias candle → next flip"
        % (anchor.sessions[0], anchor.sessions[-1], anchor.n_flips),
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=8)
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


def plot_15m_week(
    anchor: WeekAnchor,
    bars15: Dict[date, pd.DataFrame],
    all_flips: List[BiasFlip],
    out_path: Path,
) -> bool:
    plot = _concat_days(bars15, anchor.sessions)
    if len(plot) < 20:
        return False

    fig, ax = plt.subplots(figsize=(18, 9))
    x = _draw_candles(ax, plot)

    t0, t1 = plot.index[0], plot.index[-1]
    # flips that define horizontals intersecting this window:
    # include last flip before window (level may already be active) + in-window flips
    prior = [f for f in all_flips if f.ts < t0]
    relevant = ([prior[-1]] if prior else []) + [f for f in all_flips if t0 <= f.ts <= t1]

    labeled_v = False
    labeled_h = {"buy": False, "sell": False}
    for i, fl in enumerate(relevant):
        # end of this key segment = next flip or end of plot
        end_ts = relevant[i + 1].ts if i + 1 < len(relevant) else t1
        i0 = _xi(plot, fl.ts, 15)
        i1 = _xi(plot, end_ts, 15)
        if i0 is None:
            i0 = 0 if fl.ts < t0 else None
        if i1 is None:
            i1 = len(plot) - 1
        if i0 is None:
            continue
        # vertical only for flips inside the week
        if fl.ts >= t0:
            ax.axvline(
                i0,
                color=BIAS_VLINE,
                lw=1.8,
                ls="-",
                zorder=5,
                label="bias change" if not labeled_v else None,
            )
            labeled_v = True

        if fl.key is None:
            continue
        color = BUY_KEY if fl.program == "buy" else SELL_KEY
        lab = "%s key" % fl.program
        ax.hlines(
            float(fl.key),
            xmin=i0,
            xmax=max(i1, i0 + 1),
            colors=color,
            lw=2.0,
            zorder=6,
            label=lab if not labeled_h[fl.program] else None,
        )
        labeled_h[fl.program] = True
        # annotate at start of segment
        ax.text(
            i0 + 0.5,
            float(fl.key),
            " %s %.0f" % (fl.program, float(fl.key)),
            color=color,
            fontsize=7,
            va="bottom",
            zorder=7,
        )

    _session_seps(ax, plot, anchor.sessions)

    ax.set_title(
        "NQ 15m | week %s → %s | %d bias flip(s) | v-line @ flip · h-line = structure key until next flip"
        % (anchor.sessions[0], anchor.sessions[-1], anchor.n_flips),
        fontsize=10,
    )
    ax.legend(loc="upper left", fontsize=8)
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


def _write_readme(out: Path, kind: str, n: int, n_flips: int) -> None:
    if kind == "1h":
        body = [
            "# Bias month charts — 1 hour",
            "",
            "Each chart: **~1 RTH month** (~%d sessions) of **1-hour** candles." % MONTH_SESSIONS,
            "",
            "- Background **blue** = buy bias · **pink** = sell bias",
            "- Black vertical = bias flip (15m program)",
            "- At the **1h candle containing the flip**, its **high and low** are projected",
            "  as horizontals (range) until the next bias change",
            "",
            "%d charts from %d total bias flips (time-stratified)." % (n, n_flips),
            "",
            "Sibling 15m week pack: `../bias_weeks_15m/`.",
        ]
    else:
        body = [
            "# Bias week charts — 15 minute",
            "",
            "Each chart: **1 RTH week** (~5 sessions) of **15-minute** candles.",
            "",
            "- **Black vertical** = exact 15m bias flip",
            "- **Horizontal** = active structure key at that flip; drawn until the next flip",
            "  (blue = buy/LL key, maroon = sell/HH key)",
            "",
            "%d charts from %d total bias flips (time-stratified)." % (n, n_flips),
            "",
            "Paired with `../bias_weeks_1h/` (same chart ids / weeks).",
        ]
    (out / "README.md").write_text("\n".join(body) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--out-1h", default=str(OUT_1H))
    ap.add_argument("--out-15m", default=str(OUT_15M))
    ap.add_argument("--pack", choices=["both", "1h", "15m"], default="both")
    args = ap.parse_args()

    out_1h = Path(args.out_1h)
    out_15m = Path(args.out_15m)
    packs = []
    if args.pack in {"both", "1h"}:
        packs.append(out_1h)
    if args.pack in {"both", "15m"}:
        packs.append(out_15m)
    for out in packs:
        (out / "charts").mkdir(parents=True, exist_ok=True)
        for old in (out / "charts").glob("*.png"):
            old.unlink()

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    flips, bars15, bars1h = collect_flips(gby, start, end)
    all_days = sorted(bars15.keys())
    # 1h pack uses ~month windows; 15m pack stays at week (when both, prefer month for shared ids)
    sessions_per = MONTH_SESSIONS if args.pack in {"1h", "both"} else WEEK_SESSIONS
    if args.pack == "15m":
        sessions_per = WEEK_SESSIONS
    anchors = select_week_anchors(flips, all_days, args.n, sessions_per_chart=sessions_per)
    print(
        "Selected %d anchors (%d sessions/chart)" % (len(anchors), sessions_per),
        flush=True,
    )

    flips_df = pd.DataFrame(
        [
            {
                "flip_id": f.flip_id,
                "ts": f.ts,
                "program": f.program,
                "prev_program": f.prev_program,
                "key": f.key,
                "bottom": f.bottom,
                "top": f.top,
            }
            for f in flips
        ]
    )
    weeks_df = pd.DataFrame(
        [
            {
                "chart_id": a.chart_id,
                "window_start": a.sessions[0],
                "window_end": a.sessions[-1],
                "n_sessions": len(a.sessions),
                "n_flips": a.n_flips,
                "primary_flip_id": a.primary_flip_id,
                "programs": ",".join(f.program for f in a.flips),
            }
            for a in anchors
        ]
    )
    for out in packs:
        flips_df.to_csv(out / "flips.csv", index=False)
        weeks_df.to_csv(out / "charted_weeks.csv", index=False)

    ok_1h = ok_15m = 0
    idx_1h = ["# 1h bias month charts", "", "| # | file | window | flips |", "|--:|---|---|---:|"]
    idx_15 = ["# 15m bias week charts", "", "| # | file | week | flips |", "|--:|---|---|---:|"]
    do_1h = args.pack in {"both", "1h"}
    do_15 = args.pack in {"both", "15m"}

    for a in anchors:
        ws, we = a.sessions[0], a.sessions[-1]
        base = "%03d_%s_%s_flips%d" % (a.chart_id, ws, we, a.n_flips)
        f1 = "%s.png" % base
        f15 = "%s.png" % base
        if do_1h and plot_1h_week(a, bars1h, flips, out_1h / "charts" / f1):
            ok_1h += 1
            idx_1h.append("| %d | `%s` | %s→%s | %d |" % (a.chart_id, f1, ws, we, a.n_flips))
        if do_15 and plot_15m_week(a, bars15, flips, out_15m / "charts" / f15):
            ok_15m += 1
            idx_15.append("| %d | `%s` | %s→%s | %d |" % (a.chart_id, f15, ws, we, a.n_flips))
        if a.chart_id % 25 == 0:
            print("  charted %d/%d (1h=%d 15m=%d)" % (a.chart_id, len(anchors), ok_1h, ok_15m), flush=True)

    if do_1h:
        (out_1h / "charts" / "INDEX.md").write_text("\n".join(idx_1h) + "\n")
        _write_readme(out_1h, "1h", ok_1h, len(flips))
        print("Wrote 1h=%d → %s" % (ok_1h, out_1h), flush=True)
    if do_15:
        (out_15m / "charts" / "INDEX.md").write_text("\n".join(idx_15) + "\n")
        _write_readme(out_15m, "15m", ok_15m, len(flips))
        print("Wrote 15m=%d → %s" % (ok_15m, out_15m), flush=True)


if __name__ == "__main__":
    main()
