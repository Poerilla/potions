"""4h structure-program bias charts (no trades).

Runs StructureProgramEngine on **4-hour** RTH bars (same L-H-LL-HH / takeout
rules as 15m). **One chart per calendar quarter** (non-overlapping) with:

  - buy/sell bias background shade
  - vertical at each 4h-program flip
  - H/L of the **4h bias-change candle** projected until the next flip
  - **4h SuperTrend** trail (ATR 14×3)

Usage:
  python -m live.structure_program_st_chart_bias_4h --start 2020-01-01
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
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    StructureProgramEngine,
    confirm_swings,
    rth_slice,
    try_form_structures,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st" / "bias_4h_3mo"
NY = "America/New_York"
LOOKBACK_DAYS = 40  # 4h swing confirmation across days
MIN_SESSIONS = 10

BUY_SHADE = "#bbdefb"
SELL_SHADE = "#f8bbd0"
BUY_KEY = "#0d47a1"
SELL_KEY = "#880e4f"
BIAS_VLINE = "#212121"
ST_BULL = "#009c5b"
ST_BEAR = "#d62728"


@dataclass
class BiasFlip:
    flip_id: int
    ts: pd.Timestamp
    program: str
    prev_program: Optional[str]
    high: float
    low: float
    bar_ts: pd.Timestamp
    key: Optional[float] = None


@dataclass
class ChartAnchor:
    chart_id: int
    anchor_date: date
    sessions: List[date]
    flips: List[BiasFlip]
    n_flips: int
    primary_flip_id: int
    quarter_label: str  # e.g. "2023Q1"


def to_4h(rth_1m: pd.DataFrame) -> pd.DataFrame:
    if rth_1m is None or rth_1m.empty:
        return pd.DataFrame()
    ohlc = rth_1m.resample("4h", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in rth_1m.columns else ("close", "count"),
    )
    return ohlc.dropna(subset=["open", "high", "low", "close"])


def _ny_date(ts: pd.Timestamp) -> date:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.date()


def _active_key(engine: StructureProgramEngine) -> Optional[float]:
    if engine.program == "buy":
        st = engine.latest("bull")
        return float(st.key) if st is not None else None
    if engine.program == "sell":
        st = engine.latest("bear")
        return float(st.key) if st is not None else None
    return None


def _ingest_4h_day(
    engine: StructureProgramEngine,
    day_4h: pd.DataFrame,
    lookback: List[pd.DataFrame],
) -> List[Tuple[pd.Timestamp, str, Optional[str], float, float, pd.Timestamp, Optional[float]]]:
    """Ingest one day of 4h bars with lookback for swing confirms.

    Returns list of (flip_ts, program, prev_program, high, low, bar_ts, key).
    """
    frames = [b for b in lookback if b is not None and not b.empty]
    if day_4h is not None and not day_4h.empty:
        frames.append(day_4h)
    if not frames or day_4h is None or day_4h.empty:
        return []
    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    day_start = day_4h.index[0]

    day_swings = confirm_swings(combined)
    by_confirm: Dict[pd.Timestamp, list] = {}
    for sw in day_swings:
        if sw[0] < day_start:
            continue
        by_confirm.setdefault(sw[0], []).append(sw)

    flips = []
    for ts, row in day_4h.iterrows():
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
        prev_prog = engine.program
        engine._apply_takeouts_bar(ts, float(row["high"]), float(row["low"]))
        if engine.program in {"buy", "sell"} and engine.program != prev_prog and engine.ready:
            flips.append(
                (
                    ts,
                    str(engine.program),
                    prev_prog,
                    float(row["high"]),
                    float(row["low"]),
                    ts,
                    _active_key(engine),
                )
            )
    return flips


def collect_flips(
    gby: Dict[date, pd.DataFrame],
    start: Optional[date],
    end: Optional[date],
) -> Tuple[List[BiasFlip], Dict[date, pd.DataFrame]]:
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if end:
        days = [d for d in days if d <= end]

    eng = StructureProgramEngine()
    buf: List[pd.DataFrame] = []
    bars4h: Dict[date, pd.DataFrame] = {}
    flips: List[BiasFlip] = []
    fid = 0

    print("Walking 4h structure engine over %d days…" % len(days), flush=True)
    for di, d in enumerate(days, 1):
        rth = rth_slice(gby.get(d))
        if rth.empty or len(rth) < 30:
            continue
        b4 = to_4h(rth)
        if b4.empty:
            continue
        bars4h[d] = b4
        for ts, prog, prev, hi, lo, bt, key in _ingest_4h_day(eng, b4, buf[-LOOKBACK_DAYS:]):
            fid += 1
            flips.append(
                BiasFlip(
                    flip_id=fid,
                    ts=ts,
                    program=prog,
                    prev_program=prev,
                    high=hi,
                    low=lo,
                    bar_ts=bt,
                    key=key,
                )
            )
        buf.append(b4)
        buf = buf[-LOOKBACK_DAYS:]
        if di % 250 == 0:
            print(
                "  %d/%d days | flips %d | prog=%s ready=%s"
                % (di, len(days), len(flips), eng.program, eng.ready),
                flush=True,
            )

    print("Collected %d 4h bias flips" % len(flips), flush=True)
    return flips, bars4h


def session_window(all_days: List[date], anchor: date, n: int) -> List[date]:
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


def _quarter_key(d: date) -> Tuple[int, int]:
    return (d.year, (d.month - 1) // 3 + 1)


def _quarter_label(year: int, q: int) -> str:
    return "%dQ%d" % (year, q)


def select_anchors(
    flips: List[BiasFlip],
    all_days: List[date],
    n: Optional[int] = None,
) -> List[ChartAnchor]:
    """One non-overlapping chart per calendar quarter (from first-flip quarter onward)."""
    if not flips or not all_days:
        return []

    first_q = _quarter_key(_ny_date(flips[0].ts))
    by_q: Dict[Tuple[int, int], List[date]] = {}
    for d in all_days:
        qk = _quarter_key(d)
        if qk < first_q:
            continue
        by_q.setdefault(qk, []).append(d)

    keys = sorted(by_q)
    if n is not None and n > 0:
        keys = keys[:n]

    out: List[ChartAnchor] = []
    for qk in keys:
        sessions = sorted(by_q[qk])
        if len(sessions) < MIN_SESSIONS:
            continue
        start, end = sessions[0], sessions[-1]
        win_flips = [f for f in flips if start <= _ny_date(f.ts) <= end]
        if win_flips:
            primary = win_flips[0].flip_id
        else:
            prior = [f for f in flips if _ny_date(f.ts) <= start]
            primary = prior[-1].flip_id if prior else flips[0].flip_id
        out.append(
            ChartAnchor(
                chart_id=len(out) + 1,
                anchor_date=start,
                sessions=sessions,
                flips=win_flips,
                n_flips=len(win_flips),
                primary_flip_id=primary,
                quarter_label=_quarter_label(qk[0], qk[1]),
            )
        )
    return out


def build_4h_supertrend(bars4h: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    """Full-series 4h SuperTrend so each quarter chart has continuous warm trail."""
    frames = [bars4h[d] for d in sorted(bars4h) if d in bars4h and not bars4h[d].empty]
    if not frames:
        return pd.DataFrame()
    full = pd.concat(frames).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    return compute_supertrend(full, atr_len=ATR_LEN, multiplier=ATR_MULT)


def _concat_days(by_day: Dict[date, pd.DataFrame], sessions: List[date]) -> pd.DataFrame:
    frames = [by_day[d] for d in sessions if d in by_day and not by_day[d].empty]
    if not frames:
        return pd.DataFrame()
    plot = pd.concat(frames).sort_index()
    return plot[~plot.index.duplicated(keep="last")]


def _xi(plot: pd.DataFrame, ts: pd.Timestamp, bar_hours: int = 4) -> Optional[int]:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    delta = pd.Timedelta(hours=bar_hours)
    for i, bt in enumerate(plot.index):
        if bt <= ts < bt + delta:
            return i
    if not len(plot.index):
        return None
    deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(plot.index)]
    return min(deltas)[1]


def _program_spans(
    flips: List[BiasFlip],
    plot: pd.DataFrame,
    all_flips: List[BiasFlip],
) -> List[Tuple[int, int, str]]:
    if plot.empty:
        return []
    t0, t1 = plot.index[0], plot.index[-1]
    prior = [f for f in all_flips if f.ts <= t0]
    spans: List[Tuple[int, int, str]] = []
    if prior:
        cur_prog = prior[-1].program
        cur_i = 0
    else:
        cur_prog = None
        cur_i = 0
    in_window = [f for f in all_flips if t0 <= f.ts <= t1]
    for fl in in_window:
        xi = _xi(plot, fl.ts)
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
    ax.vlines(x, l, h, color="#888", lw=0.7, zorder=2)
    ax.vlines(x[up], o[up], c[up], color="#1a9850", lw=1.8, zorder=3)
    ax.vlines(x[~up], c[~up], o[~up], color="#d73027", lw=1.8, zorder=3)
    return x


def plot_chart(
    anchor: ChartAnchor,
    bars4h: Dict[date, pd.DataFrame],
    all_flips: List[BiasFlip],
    st_full: pd.DataFrame,
    out_path: Path,
) -> bool:
    plot = _concat_days(bars4h, anchor.sessions)
    if len(plot) < 12:
        return False

    fig, ax = plt.subplots(figsize=(22, 9))
    x = _draw_candles(ax, plot)

    spans = _program_spans(anchor.flips, plot, all_flips)
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

    if st_full is not None and not st_full.empty and "supertrend" in st_full.columns:
        st_win = st_full.reindex(plot.index)
        bull = st_win["supertrend"].where(st_win["supertrend_trend"] == 1)
        bear = st_win["supertrend"].where(st_win["supertrend_trend"] == -1)
        ax.plot(
            x,
            bull.to_numpy(),
            color=ST_BULL,
            lw=1.6,
            zorder=4,
            label="4h ST %d×%g bull" % (ATR_LEN, ATR_MULT),
        )
        ax.plot(
            x,
            bear.to_numpy(),
            color=ST_BEAR,
            lw=1.6,
            zorder=4,
            label="4h ST %d×%g bear" % (ATR_LEN, ATR_MULT),
        )

    t0, t1 = plot.index[0], plot.index[-1]
    prior = [f for f in all_flips if f.ts < t0]
    relevant = ([prior[-1]] if prior else []) + [f for f in all_flips if t0 <= f.ts <= t1]

    labeled_range = False
    labeled_v = False
    for i, fl in enumerate(relevant):
        end_ts = relevant[i + 1].ts if i + 1 < len(relevant) else t1
        if fl.ts < t0:
            i0 = 0
        else:
            i0 = _xi(plot, fl.bar_ts)
            if i0 is None:
                i0 = _xi(plot, fl.ts)
        i1 = _xi(plot, end_ts)
        if i1 is None:
            i1 = len(plot) - 1
        if i0 is None:
            continue
        i1 = max(i1, i0 + 1)

        color = BUY_KEY if fl.program == "buy" else SELL_KEY
        ax.hlines(
            fl.high,
            xmin=i0,
            xmax=i1,
            colors=color,
            lw=1.8,
            zorder=6,
            label="4h bias-candle H/L" if not labeled_range else None,
        )
        ax.hlines(fl.low, xmin=i0, xmax=i1, colors=color, lw=1.8, zorder=6)
        ax.fill_between([i0, i1], [fl.low, fl.low], [fl.high, fl.high], color=color, alpha=0.08, zorder=1)
        labeled_range = True
        ax.text(i0 + 0.3, fl.high, " %s H %.0f" % (fl.program, fl.high), color=color, fontsize=7, va="bottom")
        ax.text(i0 + 0.3, fl.low, " %s L %.0f" % (fl.program, fl.low), color=color, fontsize=7, va="top")

        if fl.ts >= t0:
            xi = _xi(plot, fl.ts)
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

    for d in anchor.sessions[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bdbdbd", lw=0.6, ls="--", zorder=0)
                break

    ax.set_title(
        "NQ 4h structure | %s | %s → %s | %d bias flip(s) | ST ATR(%d)×%g"
        % (
            anchor.quarter_label,
            anchor.sessions[0],
            anchor.sessions[-1],
            anchor.n_flips,
            ATR_LEN,
            ATR_MULT,
        ),
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument(
        "--n",
        type=int,
        default=0,
        help="Max quarters to chart (0 = all non-overlapping calendar quarters)",
    )
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
    flips, bars4h = collect_flips(gby, start, end)
    all_days = sorted(bars4h.keys())
    n = args.n if args.n and args.n > 0 else None
    anchors = select_anchors(flips, all_days, n)
    print(
        "Selected %d non-overlapping calendar quarters" % len(anchors),
        flush=True,
    )
    print("Computing 4h SuperTrend ATR(%d)×%g…" % (ATR_LEN, ATR_MULT), flush=True)
    st_full = build_4h_supertrend(bars4h)

    pd.DataFrame(
        [
            {
                "flip_id": f.flip_id,
                "ts": f.ts,
                "program": f.program,
                "prev_program": f.prev_program,
                "high": f.high,
                "low": f.low,
                "bar_ts": f.bar_ts,
                "key": f.key,
            }
            for f in flips
        ]
    ).to_csv(out / "flips.csv", index=False)
    pd.DataFrame(
        [
            {
                "chart_id": a.chart_id,
                "quarter": a.quarter_label,
                "window_start": a.sessions[0],
                "window_end": a.sessions[-1],
                "n_sessions": len(a.sessions),
                "n_flips": a.n_flips,
                "primary_flip_id": a.primary_flip_id,
                "programs": ",".join(f.program for f in a.flips),
            }
            for a in anchors
        ]
    ).to_csv(out / "charted_windows.csv", index=False)

    ok = 0
    idx = [
        "# 4h bias — one chart per calendar quarter",
        "",
        "| # | quarter | file | window | flips |",
        "|--:|---|---|---|---:|",
    ]
    for a in anchors:
        ws, we = a.sessions[0], a.sessions[-1]
        fname = "%03d_%s_%s_%s_flips%d.png" % (
            a.chart_id,
            a.quarter_label,
            ws,
            we,
            a.n_flips,
        )
        if plot_chart(a, bars4h, flips, st_full, chart_dir / fname):
            ok += 1
            idx.append(
                "| %d | %s | `%s` | %s→%s | %d |"
                % (a.chart_id, a.quarter_label, fname, ws, we, a.n_flips)
            )
        print("  charted %d/%d (%s)" % (a.chart_id, len(anchors), a.quarter_label), flush=True)

    (chart_dir / "INDEX.md").write_text("\n".join(idx) + "\n")
    (out / "README.md").write_text(
        "\n".join(
            [
                "# Bias charts — 4 hour structure program",
                "",
                "StructureProgramEngine on **4h** RTH bars (same swing/takeout rules as 15m).",
                "**One chart per calendar quarter** (non-overlapping).",
                "",
                "- Background **blue** = buy bias · **pink** = sell bias",
                "- Black vertical = 4h program flip",
                "- Horizontals = **4h bias-change candle** high/low until next flip",
                "- Green/red trail = **4h SuperTrend** ATR(%d)×%g" % (ATR_LEN, ATR_MULT),
                "",
                "%d quarter charts · %d raw 4h flips." % (ok, len(flips)),
                "",
            ]
        )
        + "\n"
    )
    print("Wrote %d charts → %s" % (ok, out), flush=True)


if __name__ == "__main__":
    main()
