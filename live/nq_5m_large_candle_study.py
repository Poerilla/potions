"""NQ RTH 5m large-candle study: percentile size + 3R follow from close.

Classify every Regular Trading Hours (09:30–16:00 America/New_York) 5-minute
candle as ≥p90 / ≥p80 of causal expanding range (warmup = 1 year of RTH 5m).
If p90 days are too rare (<8% of sessions), promote p80 as the chart sleeve.

Trade (diagnostic, not broker): on a large directional candle, enter at its
close, stop at its open, target = 3R (3× body). Walk subsequent 5m bars.
Same-bar SL+TP → stop first. Flatten at 16:00. One trade at a time.

Charts: full RTH 5m session, only days with ≥1 large candle. Cap via
``--max-charts`` (stratified by year + 50W/50L). All classifications stay in CSV.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_5m_large_candle_study --email
  python -m live.nq_5m_large_candle_study --email --smoke
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .gbpusd_quarterly_4h_charts import wilder_atr
from .notify_email import send_email

HUB = REPO / "live" / "state" / "nq_5m_large_candle"
NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
ENTRY_CUTOFF = time(15, 45)
POINT_VALUE = 20.0
FEE = 1.50
TICK = 0.25
WARMUP_BARS = 78 * 252  # ~1y of RTH 5m
MIN_WARMUP = 78 * 60
RARE_DAY_FRAC = 0.08
MIN_EVENTS = 80  # trades/bars: below this, fall back from hi percentile to lo
MAX_CHARTS_DEFAULT = 220
NQ_5M_CSV = REPO / "nq" / "nq_5min_rth.csv"


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def score_nets(nets: np.ndarray) -> Dict[str, float]:
    nets = np.asarray(nets, dtype=float)
    if nets.size == 0:
        return {"n": 0, "net": 0.0, "stress": 0.0, "ns": 0.0, "wr": 0.0, "avg": 0.0, "wins": 0}
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    stress = float(abs((eq - peak).min()))
    net = float(nets.sum())
    wins = nets[nets > 0].sum()
    losses = nets[nets <= 0].sum()
    return {
        "n": int(nets.size),
        "net": net,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
        "wr": float((nets > 0).mean()),
        "avg": float(nets.mean()),
        "wins": int((nets > 0).sum()),
        "pf": (abs(wins / losses) if losses < 0 else 99.0),
    }


def load_rth_5m(*, progress: bool = True) -> pd.DataFrame:
    if progress:
        _progress("load %s" % NQ_5M_CSV)
    df = pd.read_csv(NQ_5M_CSV)
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df["ts_event"], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    out = pd.DataFrame(
        {
            "ts": ts,
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
            if "volume" in df.columns
            else 0.0,
        }
    ).dropna(subset=["ts", "open", "high", "low", "close"])
    t = out["ts"].dt.time
    out = out[(t >= RTH_OPEN) & (t < RTH_CLOSE)].sort_values("ts").drop_duplicates("ts")
    out = decorate_ohlc(out.reset_index(drop=True))
    if progress:
        _progress("  RTH 5m bars=%s days=%s" % (f"{len(out):,}", out["session_date"].nunique()))
    return out


def decorate_ohlc(out: pd.DataFrame) -> pd.DataFrame:
    """Session date, range/body/dir, causal ATR on an OHLC frame with ``ts``."""
    out = out.copy()
    ts = pd.to_datetime(out["ts"])
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
    else:
        ts = ts.dt.tz_convert(NY)
    out["ts"] = ts
    out = out.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    out["session_date"] = out["ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    out["hour"] = out["ts"].dt.hour
    out["minute"] = out["ts"].dt.minute
    out["range"] = (out["high"] - out["low"]).astype(float)
    out["body"] = (out["close"] - out["open"]).abs().astype(float)
    out["dir"] = np.where(
        out["close"] > out["open"],
        "long",
        np.where(out["close"] < out["open"], "short", "doji"),
    )
    atr = wilder_atr(out, 14)
    out["atr"] = atr
    out["atr_known"] = atr.shift(1)
    out["range_atr"] = out["range"] / out["atr_known"].replace(0, np.nan)
    return out


def resample_rth(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Left-label RTH resample of a decorated 5m frame (15 or 60)."""
    g = df.set_index("ts").sort_index()
    ohlc = g.resample("%dmin" % int(minutes), label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in g.columns else ("open", "size"),
    )
    out = ohlc.dropna(subset=["open", "high", "low", "close"]).reset_index()
    t = pd.to_datetime(out["ts"]).dt.tz_convert(NY).dt.time
    out = out[(t >= RTH_OPEN) & (t < RTH_CLOSE)]
    return decorate_ohlc(out)


def causal_expanding_threshold(values: np.ndarray, q: float, min_periods: int) -> np.ndarray:
    """Expanding quantile using prior bars only (shift 1)."""
    s = pd.Series(values, dtype=float)
    return s.shift(1).expanding(min_periods=min_periods).quantile(q).to_numpy()


def pct_name(q: float) -> str:
    """0.99 → 'p99', 99 → 'p99'."""
    qq = float(q)
    if qq > 1.0:
        qq = qq / 100.0
    return "p%d" % int(round(qq * 100))


def classify(
    df: pd.DataFrame,
    min_warmup: Optional[int] = None,
    extra_qs: Sequence[float] = (),
) -> pd.DataFrame:
    """Causal expanding range flags. Always p90/p80; ``extra_qs`` adds e.g. 0.99/0.95."""
    out = df.copy()
    mw = MIN_WARMUP if min_warmup is None else int(min_warmup)
    rng = out["range"].to_numpy(float)
    ra = out["range_atr"].to_numpy(float)
    qs: List[float] = [0.90, 0.80]
    for q in extra_qs:
        qq = float(q)
        if qq > 1.0:
            qq = qq / 100.0
        qs.append(qq)
    seen = set()
    for q in qs:
        if q in seen:
            continue
        seen.add(q)
        name = pct_name(q)
        out["%s_thr" % name] = causal_expanding_threshold(rng, q, mw)
        out["is_%s" % name] = (out["range"] >= out["%s_thr" % name]) & out["%s_thr" % name].notna()
        out["%s_atr_thr" % name] = causal_expanding_threshold(ra, q, mw)
        out["is_%s_atr" % name] = (out["range_atr"] >= out["%s_atr_thr" % name]) & out[
            "%s_atr_thr" % name
        ].notna()
    return out


def choose_pct_sleeve(
    cov: pd.DataFrame,
    hi: str,
    lo: str,
    *,
    rare_day_frac: float = RARE_DAY_FRAC,
    min_events: int = MIN_EVENTS,
) -> Tuple[str, dict]:
    """Pick ``is_{hi}`` unless days/events are too rare, then ``is_{lo}``.

    ``hi``/``lo`` are names like ``p99`` / ``p95``.
    """
    n_days = int(len(cov))
    has_hi = "has_%s" % hi
    n_hi_col = "n_%s" % hi
    n_hi_days = int(cov[has_hi].sum()) if has_hi in cov.columns and n_days else 0
    n_hi_bars = int(cov[n_hi_col].sum()) if n_hi_col in cov.columns else 0
    frac = n_hi_days / max(n_days, 1)
    enough_days = frac >= float(rare_day_frac)
    enough_n = n_hi_bars >= int(min_events)
    use_hi = enough_days and enough_n
    meta = {
        "hi": hi,
        "lo": lo,
        "n_days": n_days,
        "n_hi_days": n_hi_days,
        "n_hi_bars": n_hi_bars,
        "hi_day_frac": frac,
        "enough_days": enough_days,
        "enough_n": enough_n,
        "use_hi": use_hi,
        "reason": (
            "hi"
            if use_hi
            else (
                "hi days too rare (%.1f%% < %.0f%%)" % (100 * frac, 100 * rare_day_frac)
                if not enough_days
                else "hi events %d < min %d" % (n_hi_bars, min_events)
            )
        ),
    }
    return ("is_%s" % hi if use_hi else "is_%s" % lo), meta


def walk_trades(
    df: pd.DataFrame,
    flag_col: str,
    *,
    r_mult: float = 3.0,
    fade: bool = False,
    entry_cutoff: Optional[time] = None,
) -> pd.DataFrame:
    """Non-overlapping R-multiple of flagged directional candles.

    Follow: enter at close, SL at open, TP = r_mult × body, same side as candle.
    Fade: enter at close opposite the candle; SL is the reflection of open
    across close (same body risk); TP = r_mult × body the other way.
    """
    rows: List[dict] = []
    by_day = {d: g.reset_index(drop=True) for d, g in df.groupby("session_date", sort=False)}
    for day, sess in by_day.items():
        busy_until = -1
        highs = sess["high"].to_numpy(float)
        lows = sess["low"].to_numpy(float)
        closes = sess["close"].to_numpy(float)
        opens = sess["open"].to_numpy(float)
        flags = sess[flag_col].to_numpy()
        dirs = sess["dir"].to_numpy()
        times = sess["ts"]
        for i in range(len(sess) - 1):
            if i <= busy_until:
                continue
            if not bool(flags[i]):
                continue
            candle_side = str(dirs[i])
            if candle_side not in ("long", "short"):
                continue
            ts = pd.Timestamp(times.iloc[i])
            if ts.tzinfo is None:
                ts = ts.tz_localize(NY)
            else:
                ts = ts.tz_convert(NY)
            cutoff = ENTRY_CUTOFF if entry_cutoff is None else entry_cutoff
            if ts.time() >= cutoff:
                continue
            body = abs(closes[i] - opens[i])
            if body < TICK:
                continue
            if fade:
                side = "short" if candle_side == "long" else "long"
                entry = closes[i]
                sl = 2.0 * closes[i] - opens[i]
            else:
                side = candle_side
                entry = closes[i]
                sl = opens[i]
            direction = 1 if side == "long" else -1
            tp = entry + direction * float(r_mult) * body
            reason = "eod"
            exit_px = closes[-1]
            exit_i = len(sess) - 1
            for j in range(i + 1, len(sess)):
                hit_sl = lows[j] <= sl if side == "long" else highs[j] >= sl
                hit_tp = highs[j] >= tp if side == "long" else lows[j] <= tp
                if hit_sl and hit_tp:
                    exit_px, reason, exit_i = sl, "stop", j
                    break
                if hit_sl:
                    exit_px, reason, exit_i = sl, "stop", j
                    break
                if hit_tp:
                    exit_px, reason, exit_i = tp, "target", j
                    break
            pts = (exit_px - entry) * direction
            net = pts * POINT_VALUE - FEE
            rows.append(
                {
                    "session_date": day,
                    "signal_ts": times.iloc[i],
                    "exit_ts": times.iloc[exit_i],
                    "side": side,
                    "candle_side": candle_side,
                    "fade": bool(fade),
                    "target_r": float(r_mult),
                    "flag": flag_col,
                    "range": float(sess["range"].iloc[i]),
                    "body": body,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "exit_px": float(exit_px),
                    "reason": reason,
                    "r_mult": pts / body,
                    "net_usd": net,
                    "win": net > 0,
                    "hour": int(sess["hour"].iloc[i]),
                    "year": int(pd.Timestamp(day).year),
                    "signal_i": i,
                    "exit_i": exit_i,
                }
            )
            busy_until = exit_i
    return pd.DataFrame(rows)


def control_all_candles(
    df: pd.DataFrame,
    n_match: int,
    seed: int = 20260818,
    *,
    entry_cutoff: Optional[time] = None,
    flag_col: str = "is_p90",
    thr_col: Optional[str] = None,
) -> pd.DataFrame:
    """Random non-large directional candles, same count as the large book."""
    name = flag_col[3:] if flag_col.startswith("is_") else flag_col
    thr = thr_col or ("%s_thr" % name)
    if flag_col not in df.columns or thr not in df.columns:
        return pd.DataFrame()
    pool = df[(df["dir"] != "doji") & (~df[flag_col].astype(bool)) & df[thr].notna()].copy()
    if pool.empty or n_match <= 0:
        return pd.DataFrame()
    take = min(n_match, len(pool))
    samp = pool.sample(n=take, random_state=seed)
    dummy = df.copy()
    dummy["is_ctrl"] = False
    dummy.loc[samp.index, "is_ctrl"] = True
    return walk_trades(dummy, "is_ctrl", entry_cutoff=entry_cutoff)


def summarize_book(trades: pd.DataFrame, label: str) -> dict:
    if trades is None or trades.empty:
        return {"label": label, "n": 0}
    sc = score_nets(trades["net_usd"].to_numpy(float))
    reasons = trades["reason"].value_counts().to_dict()
    sc.update(
        {
            "label": label,
            "target_n": int(reasons.get("target", 0)),
            "stop_n": int(reasons.get("stop", 0)),
            "eod_n": int(reasons.get("eod", 0)),
            "avg_r": float(trades["r_mult"].mean()),
            "days": int(trades["session_date"].nunique()),
        }
    )
    return sc


def day_coverage(df: pd.DataFrame) -> pd.DataFrame:
    agg: Dict[str, Tuple[str, str]] = {
        "n_bars": ("ts", "size"),
        "max_range": ("range", "max"),
        "year": ("ts", lambda s: int(s.dt.year.iloc[0])),
    }
    for col in df.columns:
        if col.startswith("is_"):
            agg["n_" + col[3:]] = (col, "sum")
    g = df.groupby("session_date", sort=False).agg(**agg)
    for col in list(g.columns):
        if col.startswith("n_p") and not col.endswith("_atr"):
            g["has_" + col[2:]] = g[col] > 0
    return g.reset_index()


def choose_chart_days(
    cov: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    flag: str,
    max_charts: int,
) -> List[str]:
    name = flag[3:] if flag.startswith("is_") else flag
    col = "has_%s" % name
    if col not in cov.columns:
        col = "has_p90" if "has_p90" in cov.columns else cov.columns[1]
    days = cov.loc[cov[col], "session_date"].tolist()
    if len(days) <= max_charts:
        return days
    chosen: List[str] = []
    # 50W / 50L from trades
    if trades is not None and not trades.empty:
        wins = trades[trades["win"]].sort_values("net_usd", ascending=False)
        losses = trades[~trades["win"]].sort_values("net_usd")
        for frame, k in ((wins, 50), (losses, 50)):
            for d in frame["session_date"].drop_duplicates().head(k):
                if d not in chosen:
                    chosen.append(d)
    remaining = [d for d in days if d not in chosen]
    cov_rem = cov[cov["session_date"].isin(remaining)]
    need = max_charts - len(chosen)
    if need > 0 and not cov_rem.empty:
        years = sorted(cov_rem["year"].unique())
        per = max(1, need // max(len(years), 1))
        extra: List[str] = []
        for y in years:
            part = cov_rem[cov_rem["year"] == y]["session_date"].tolist()
            step = max(1, len(part) // per)
            extra.extend(part[::step][:per])
        for d in extra:
            if d not in chosen:
                chosen.append(d)
            if len(chosen) >= max_charts:
                break
    return chosen[:max_charts]


def _plot_session(
    sess: pd.DataFrame,
    trades: pd.DataFrame,
    path: Path,
    *,
    flag: str,
    p80_also: bool,
    tf_label: str = "5m",
    lo_flag: Optional[str] = None,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 7.2))
    x = np.arange(len(sess))
    o = sess["open"].to_numpy(float)
    h = sess["high"].to_numpy(float)
    l = sess["low"].to_numpy(float)
    c = sess["close"].to_numpy(float)
    up = c >= o
    # Highlight large candles first
    hi_col = flag if flag in sess.columns else "is_p90"
    lo_col = lo_flag or ("is_p80" if hi_col == "is_p90" else None)
    hi_name = hi_col[3:] if hi_col.startswith("is_") else hi_col
    for i, row in enumerate(sess.itertuples(index=False)):
        is_hi = bool(getattr(row, hi_col, False))
        is_lo = bool(getattr(row, lo_col, False)) if lo_col else False
        if is_hi:
            ax.axvspan(i - 0.45, i + 0.45, color="#ffe082", alpha=0.55, zorder=1)
        elif p80_also and is_lo:
            ax.axvspan(i - 0.45, i + 0.45, color="#fff8e1", alpha=0.4, zorder=1)
    ax.vlines(x, l, h, color=np.where(up, "#2e7d32", "#c62828"), linewidth=0.9, zorder=3)
    body_h = np.maximum(np.abs(c - o), (h.max() - l.min()) * 0.001)
    for xi, oi, ci, uu in zip(x, o, c, up):
        ax.add_patch(
            plt.Rectangle(
                (xi - 0.32, min(oi, ci)),
                0.64,
                body_h[int(xi)],
                facecolor="#2e7d32" if uu else "#c62828",
                edgecolor="#1b5e20" if uu else "#8e0000",
                linewidth=0.4,
                zorder=4,
            )
        )
    day = str(sess["session_date"].iloc[0])
    day_tr = trades[trades["session_date"] == day] if trades is not None and not trades.empty else pd.DataFrame()
    for _, tr in day_tr.iterrows():
        color = "#1565c0" if tr["side"] == "long" else "#6a1b9a"
        si = int(tr["signal_i"])
        ei = int(tr["exit_i"])
        ax.plot([si, ei], [tr["entry"], tr["exit_px"]], color=color, lw=1.2, zorder=5)
        ax.scatter([si], [tr["entry"]], marker="^" if tr["side"] == "long" else "v", color=color, s=36, zorder=6)
        ax.scatter(
            [ei],
            [tr["exit_px"]],
            marker="x",
            color="#2e7d32" if tr["win"] else "#c62828",
            s=40,
            zorder=6,
        )
        ax.axhline(tr["sl"], color="#ef6c00", ls=":", lw=0.7, alpha=0.7)
        ax.axhline(tr["tp"], color="#0277bd", ls="--", lw=0.7, alpha=0.55)
    ax.set_xlim(-1, len(sess))
    ax.set_title(
        "NQ %s RTH %s  |  gold = %s large  |  3R follow close→SL open"
        % (tf_label, day, hi_name),
        fontsize=11,
    )
    ax.set_xlabel("%s bar (09:30 → 16:00)" % tf_label)
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def yearly_table(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    rows = []
    for y, g in trades.groupby("year"):
        sc = score_nets(g["net_usd"].to_numpy(float))
        sc["year"] = int(y)
        rows.append(sc)
    return pd.DataFrame(rows).sort_values("year")


def hour_table(trades: pd.DataFrame) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    rows = []
    for h, g in trades.groupby("hour"):
        sc = score_nets(g["net_usd"].to_numpy(float))
        sc["hour"] = int(h)
        rows.append(sc)
    return pd.DataFrame(rows).sort_values("hour")


def write_report(
    *,
    cov: pd.DataFrame,
    p90_tr: pd.DataFrame,
    p80_tr: pd.DataFrame,
    p90_atr_tr: pd.DataFrame,
    ctrl_tr: pd.DataFrame,
    all_dir_tr: pd.DataFrame,
    flag: str,
    chart_n: int,
    chart_days_n: int,
    n_bars: int,
    n_days: int,
) -> None:
    p90_days = int(cov["has_p90"].sum())
    p80_days = int(cov["has_p80"].sum())
    p90_frac = p90_days / max(n_days, 1)
    books = [
        summarize_book(p90_tr, "p90 large 3R"),
        summarize_book(p80_tr, "p80 large 3R"),
        summarize_book(p90_atr_tr, "p90 ATR-norm range 3R"),
        summarize_book(ctrl_tr, "matched non-large control"),
        summarize_book(all_dir_tr, "ALL directional 5m 3R (baseline)"),
    ]
    fair = 0.25  # 3R random WR
    lines = [
        "# NQ 5m RTH large-candle study",
        "",
        "Universe: NQ Regular Trading Hours 09:30–16:00, 5-minute candles (`nq/nq_5min_rth.csv`).",
        "Size = **high−low range**. Percentile = **causal expanding** of prior RTH 5m ranges "
        "(warmup 60 sessions; thresholds from history before the bar).",
        "",
        "Trade: follow candle direction from **close**, SL at **open**, TP = **3× body**. "
        "Non-overlapping. Same-bar stop before target. Flatten 16:00. $1.50 fee, $20/pt.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| RTH 5m bars | %s |" % f"{n_bars:,}",
        "| Sessions | %s |" % f"{n_days:,}",
        "| Bars ≥p90 | %s (%.1f%%) |"
        % (f"{int(cov['n_p90'].sum()):,}", 100.0 * float(cov["n_p90"].sum()) / max(n_bars, 1)),
        "| Days with ≥1 p90 | %d (%.1f%% of days) |" % (p90_days, 100 * p90_frac),
        "| Days with ≥1 p80 | %d (%.1f%% of days) |" % (p80_days, 100 * p80_days / max(n_days, 1)),
        "| Chart sleeve | **%s** |" % ("p90" if flag == "is_p90" else "p80 (p90 days too rare)"),
        "| Charts written | %d / %d qualifying days (stratified sample: 50W/50L + yearly) |" % (chart_n, chart_days_n),
        "",
        "Fair 3R WR with no edge ≈ **25%**. If large-candle WR sits near that (or below the all-candle book), size is not a directional signal.",
        "",
        "## Books",
        "",
        "| Book | n | WR | avg | net | stress | N/S | PF | avg R | tgt/stop/eod |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: NQ 5m large-candle 3R study complete",
        "",
        "Hub: %s" % HUB.resolve(),
        "Chart sleeve: %s" % ("p90" if flag == "is_p90" else "p80"),
        "Days with p90: %d / %d (%.0f%%)" % (p90_days, n_days, 100 * p90_frac),
        "",
    ]
    for b in books:
        if not b.get("n"):
            lines.append("| %s | 0 | — | — | — | — | — | — | — | — |" % b["label"])
            continue
        lines.append(
            "| %s | %d | %.1f%% | $%.0f | $%.0f | $%.0f | %.2f | %.2f | %.2f | %d/%d/%d |"
            % (
                b["label"],
                b["n"],
                100 * b["wr"],
                b["avg"],
                b["net"],
                b["stress"],
                b["ns"],
                b["pf"],
                b["avg_r"],
                b.get("target_n", 0),
                b.get("stop_n", 0),
                b.get("eod_n", 0),
            )
        )
        email.append(
            "%s  n=%d WR=%.0f%% net=$%.0f N/S=%.2f PF=%.2f"
            % (b["label"], b["n"], 100 * b["wr"], b["net"], b["ns"], b["pf"])
        )
    p90s = books[0]
    stance = "no directional edge vs 25% fair 3R"
    if p90s.get("n", 0) >= 80:
        if p90s["wr"] >= 0.32 and p90s["ns"] >= 1.2:
            stance = "curious lift vs fair 3R — still diagnostic; do not promote"
        elif p90s["wr"] <= 0.22 or p90s["net"] < 0:
            stance = "large candles look like **exhaustion / mean-revert**, not follow-through"
        else:
            stance = "WR near fair 3R — size does not mean follow-through"
    lines += [
        "",
        "**Stance:** %s." % stance,
        "",
        "## Yearly (chart sleeve trades)",
        "",
    ]
    email.append("")
    email.append("Stance: %s" % stance)
    yt = yearly_table(p90_tr if flag == "is_p90" else p80_tr)
    if not yt.empty:
        lines += [
            "| Year | n | WR | net | N/S |",
            "|---:|---:|---:|---:|---:|",
        ]
        for _, r in yt.iterrows():
            lines.append(
                "| %d | %d | %.1f%% | $%.0f | %.2f |"
                % (int(r["year"]), int(r["n"]), 100 * float(r["wr"]), float(r["net"]), float(r["ns"]))
            )
        lines.append("")
    ht = hour_table(p90_tr if flag == "is_p90" else p80_tr)
    if not ht.empty:
        lines += [
            "## By NY hour (signal bar)",
            "",
            "| Hour | n | WR | avg | net |",
            "|---:|---:|---:|---:|---:|",
        ]
        for _, r in ht.iterrows():
            lines.append(
                "| %d | %d | %.1f%% | $%.0f | $%.0f |"
                % (int(r["hour"]), int(r["n"]), 100 * float(r["wr"]), float(r["avg"]), float(r["net"]))
            )
        lines.append("")
    lines += [
        "## Charts",
        "",
        "Gold highlight = large candle (chart sleeve). Blue/purple markers = 3R entry/exit.",
        "Index: [`charts/INDEX.md`](charts/INDEX.md).",
        "",
        "Hub: `%s`" % HUB.resolve(),
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    if not yt.empty:
        yt.to_csv(HUB / "yearly.csv", index=False)
    if not ht.empty:
        ht.to_csv(HUB / "by_hour.csv", index=False)


def write_chart_index(days: Sequence[str], trades: pd.DataFrame, cov: pd.DataFrame) -> None:
    root = HUB / "charts"
    lines = [
        "# NQ 5m RTH large-candle charts",
        "",
        "Full session 09:30–16:00. Gold = large candle. Only qualifying days (sampled if over cap).",
        "",
        "| # | Day | n large | 3R n | 3R net | Chart |",
        "|---:|---|---:|---:|---:|---|",
    ]
    cov_i = cov.set_index("session_date")
    for i, day in enumerate(days, 1):
        n_lg = int(cov_i.loc[day, "n_p90"] + cov_i.loc[day, "n_p80"] * 0) if day in cov_i.index else 0
        if day in cov_i.index:
            n_lg = int(cov_i.loc[day, "n_p90"] or cov_i.loc[day, "n_p80"])
        dtr = trades[trades["session_date"] == day] if trades is not None and not trades.empty else pd.DataFrame()
        net = float(dtr["net_usd"].sum()) if not dtr.empty else 0.0
        rel = "%s.png" % day
        lines.append(
            "| %d | %s | %d | %d | $%.0f | [%s](%s) |"
            % (i, day, n_lg, len(dtr), net, rel, rel)
        )
    (root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(*, email: bool, smoke: bool, max_charts: int) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        df = load_rth_5m()
        if smoke:
            # Keep last ~400 sessions after warmup headroom.
            dates = df["session_date"].drop_duplicates()
            keep = set(dates.tail(400))
            df = df[df["session_date"].isin(keep)].reset_index(drop=True)
            _progress("SMOKE bars=%s" % f"{len(df):,}")
        _progress("classify expanding p90/p80 ...")
        df = classify(df)
        ready = df[df["p90_thr"].notna()].copy()
        n_bars = int(len(ready))
        n_days = int(ready["session_date"].nunique())
        cov = day_coverage(ready)
        cov.to_csv(HUB / "day_coverage.csv", index=False)
        p90_frac = float(cov["has_p90"].mean()) if len(cov) else 0.0
        flag = "is_p90" if p90_frac >= RARE_DAY_FRAC else "is_p80"
        _progress("p90 day frac=%.1f%% → chart flag %s" % (100 * p90_frac, flag))
        # Persist candle classifications (can be large; parquet + csv head)
        ready.to_parquet(HUB / "candles.parquet", index=False)
        ready.head(5000).to_csv(HUB / "candles_head.csv", index=False)

        _progress("walk 3R p90 ...")
        p90_tr = walk_trades(ready, "is_p90")
        _progress("  p90 trades=%d" % len(p90_tr))
        _progress("walk 3R p80 ...")
        p80_tr = walk_trades(ready, "is_p80")
        _progress("  p80 trades=%d" % len(p80_tr))
        sleeve_tr = p90_tr if flag == "is_p90" else p80_tr
        if not p90_tr.empty:
            p90_tr.to_csv(HUB / "trades_p90.csv", index=False)
        if not p80_tr.empty:
            p80_tr.to_csv(HUB / "trades_p80.csv", index=False)

        _progress("walk 3R p90-atr-norm ...")
        p90_atr_tr = walk_trades(ready, "is_p90_atr")
        _progress("  p90-atr trades=%d" % len(p90_atr_tr))
        if not p90_atr_tr.empty:
            p90_atr_tr.to_csv(HUB / "trades_p90_atr.csv", index=False)
        ctrl_tr = control_all_candles(ready, n_match=int(len(p90_tr)))
        if not ctrl_tr.empty:
            ctrl_tr.to_csv(HUB / "trades_control.csv", index=False)

        _progress("all-directional 3R baseline (non-overlap) ...")
        ready["is_any_dir"] = (ready["dir"] != "doji") & ready["p90_thr"].notna()
        all_dir_tr = walk_trades(ready, "is_any_dir")
        if not all_dir_tr.empty:
            all_dir_tr.to_csv(HUB / "trades_all_directional.csv", index=False)
        _progress("  all-dir trades=%d" % len(all_dir_tr))

        chart_pool = int(cov["has_p90"].sum() if flag == "is_p90" else cov["has_p80"].sum())
        days = choose_chart_days(cov, sleeve_tr, flag=flag, max_charts=max_charts)
        _progress("charts %d days ..." % len(days))
        by_day = {d: g.reset_index(drop=True) for d, g in ready.groupby("session_date", sort=False)}
        charts_dir = HUB / "charts"
        if charts_dir.exists():
            import shutil

            shutil.rmtree(charts_dir)
        charts_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for i, day in enumerate(days, 1):
            sess = by_day.get(day)
            if sess is None or sess.empty:
                continue
            path = charts_dir / ("%s.png" % day)
            _plot_session(sess, sleeve_tr, path, flag=flag, p80_also=flag == "is_p90")
            manifest.append({"i": i, "session_date": day, "path": str(path)})
            if i % 25 == 0:
                _progress("  charted %d/%d" % (i, len(days)))
        pd.DataFrame(manifest).to_csv(HUB / "chart_manifest.csv", index=False)
        write_chart_index(days, sleeve_tr, cov)
        write_report(
            cov=cov,
            p90_tr=p90_tr,
            p80_tr=p80_tr,
            p90_atr_tr=p90_atr_tr,
            ctrl_tr=ctrl_tr,
            all_dir_tr=all_dir_tr,
            flag=flag,
            chart_n=len(manifest),
            chart_days_n=chart_pool,
            n_bars=n_bars,
            n_days=n_days,
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "flag": flag,
                    "p90_day_frac": p90_frac,
                    "charts": len(manifest),
                    "smoke": smoke,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ 5m large-candle study FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ 5m large-candle study FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ 5m large-candle 3R study complete",
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-charts", type=int, default=MAX_CHARTS_DEFAULT)
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(email=bool(args.email), smoke=bool(args.smoke), max_charts=int(args.max_charts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
