"""NQ first-hour (09:30–10:30) follow / fade + HP condition mill.

One 1-hour candle per RTH session (the opening hour only). After that candle
closes, follow its direction or fade it (1R and 3R), walking remaining RTH on
5-minute bars. Also a large *first-hour range* sleeve (default p90; ``--hi 99
--lo 95`` for tails), first-hour-native conditions, prior-opposed overlay, and
the futures HP mill.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_ha --email
  python -m live.nq_1h_first_hour_ha --email --hi 99 --lo 95
  python -m live.nq_1h_first_hour_ha --email --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
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
from .notify_email import send_email
from .nq_5m_large_candle_study import (
    FEE,
    POINT_VALUE,
    TICK,
    choose_chart_days,
    choose_pct_sleeve,
    load_rth_5m,
    pct_name,
    resample_rth,
    score_nets,
    summarize_book,
)
from .nq_large_candle_ha_lib import (
    PO_CONDS,
    annotate_campaigns,
    attach_po_context,
    attach_trade_po_labels,
    compare_current_hp,
    load_po_campaigns,
    po_buckets_table,
    profile_frame,
    trades_to_campaigns,
    write_ha_report,
)

HUB = REPO / "live" / "state" / "nq_1h_first_hour_ha"
NY = "America/New_York"
FH_OPEN = time(9, 30)
FH_CLOSE = time(10, 30)
RTH_CLOSE = time(16, 0)
MIN_FH_BARS = 10
MIN_WARMUP_DAYS = 60
MAX_CHARTS_DEFAULT = 160
FAMILY = "nq_1h_first_hour"
MIN_N = 40

FH_CONDS: Sequence[Tuple[str, str]] = (
    ("fh_size", "First-hour range size"),
    ("fh_body", "First-hour body conviction"),
    ("fh_close_third", "First-hour close location"),
    ("fh_vs_prior", "First-hour vs prior day"),
    ("or15_vs_fh", "OR15 vs first hour"),
    ("gap_vs_fh", "Gap vs first hour"),
) + tuple(PO_CONDS)


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _t(ts) -> time:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.time()


def build_first_hour(df5: pd.DataFrame) -> pd.DataFrame:
    """One row per session: 09:30–10:30 OHLC + causal first-hour conditions."""
    rows: List[dict] = []
    by_day = {d: g for d, g in df5.groupby("session_date", sort=False)}
    prior_high = prior_low = prior_close = np.nan
    hist_ranges: List[float] = []
    for day, sess in by_day.items():
        st = sess["ts"].dt.tz_convert(NY).dt.time
        fh = sess[(st >= FH_OPEN) & (st < FH_CLOSE)]
        rest = sess[st >= FH_CLOSE]
        or15 = sess[(st >= FH_OPEN) & (st < time(9, 45))]
        if len(fh) < MIN_FH_BARS or rest.empty:
            if len(sess):
                prior_high = float(sess["high"].max())
                prior_low = float(sess["low"].min())
                prior_close = float(sess["close"].iloc[-1])
            continue
        o = float(fh["open"].iloc[0])
        h = float(fh["high"].max())
        l = float(fh["low"].min())
        c = float(fh["close"].iloc[-1])
        rng = h - l
        body = abs(c - o)
        direction = "long" if c > o else ("short" if c < o else "doji")
        close_loc = (c - l) / rng if rng > TICK else 0.5
        if close_loc >= 2.0 / 3.0:
            close_third = "upper"
        elif close_loc <= 1.0 / 3.0:
            close_third = "lower"
        else:
            close_third = "mid"
        br = body / rng if rng > TICK else 0.0
        if br >= 0.66:
            body_b = "strong"
        elif br <= 0.33:
            body_b = "weak"
        else:
            body_b = "mid"
        if np.isfinite(prior_high) and rng > 0:
            if l > prior_high:
                vs_prior = "above_pdh"
            elif h < prior_low:
                vs_prior = "below_pdl"
            else:
                vs_prior = "overlap"
        else:
            vs_prior = "na"
        gap = o - prior_close if np.isfinite(prior_close) else 0.0
        if not np.isfinite(prior_close) or abs(gap) < TICK:
            gap_dir = "flat"
        elif gap > 0:
            gap_dir = "gap_up"
        else:
            gap_dir = "gap_down"
        if gap_dir == "flat" or direction == "doji":
            gap_vs = "flat"
        elif (gap_dir == "gap_up" and direction == "long") or (gap_dir == "gap_down" and direction == "short"):
            gap_vs = "gap_with"
        else:
            gap_vs = "gap_against"
        if len(or15) >= 2:
            o15 = float(or15["open"].iloc[0])
            c15 = float(or15["close"].iloc[-1])
            or15_dir = "long" if c15 > o15 else ("short" if c15 < o15 else "doji")
        else:
            or15_dir = "na"
        if or15_dir in ("long", "short") and direction in ("long", "short"):
            or15_vs = "or15_agree" if or15_dir == direction else "or15_oppose"
        else:
            or15_vs = "na"
        # causal expanding p99/p95/p90/p80 of *prior* first-hour ranges
        p99 = p95 = p90 = p80 = np.nan
        if len(hist_ranges) >= MIN_WARMUP_DAYS:
            s = pd.Series(hist_ranges, dtype=float)
            p99 = float(s.quantile(0.99))
            p95 = float(s.quantile(0.95))
            p90 = float(s.quantile(0.90))
            p80 = float(s.quantile(0.80))
        is_p99 = bool(np.isfinite(p99) and rng >= p99)
        is_p95 = bool(np.isfinite(p95) and rng >= p95)
        is_p90 = bool(np.isfinite(p90) and rng >= p90)
        is_p80 = bool(np.isfinite(p80) and rng >= p80)
        if np.isfinite(p99) and rng >= p99:
            size_b = "fh_p99"
        elif np.isfinite(p95) and rng >= p95:
            size_b = "fh_p95"
        elif np.isfinite(p90) and rng >= p90:
            size_b = "fh_p90"
        elif np.isfinite(p80) and rng >= p80:
            size_b = "fh_p80"
        elif np.isfinite(p80):
            size_b = "fh_lt_p80"
        else:
            size_b = "warmup"
        rows.append(
            {
                "session_date": day,
                "ts": fh["ts"].iloc[-1],
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": float(fh["volume"].sum()) if "volume" in fh.columns else 0.0,
                "range": rng,
                "body": body,
                "dir": direction,
                "n_bars": int(len(fh)),
                "year": int(pd.Timestamp(day).year),
                "hour": 10,
                "p99_thr": p99,
                "p95_thr": p95,
                "p90_thr": p90,
                "p80_thr": p80,
                "is_p99": is_p99,
                "is_p95": is_p95,
                "is_p90": is_p90,
                "is_p80": is_p80,
                "fh_size": size_b,
                "fh_body": body_b,
                "fh_close_third": close_third,
                "fh_vs_prior": vs_prior,
                "or15_vs_fh": or15_vs,
                "gap_vs_fh": gap_vs,
                "gap_dir": gap_dir,
            }
        )
        hist_ranges.append(rng)
        prior_high = float(sess["high"].max())
        prior_low = float(sess["low"].min())
        prior_close = float(sess["close"].iloc[-1])
    out = pd.DataFrame(rows)
    if not out.empty:
        # walk_trades-style flags for PO mill (all first hours after warmup)
        out["is_any"] = out["dir"].isin(["long", "short"]) & out["p90_thr"].notna()
    return out


def walk_first_hour(
    df5: pd.DataFrame,
    fh: pd.DataFrame,
    *,
    r_mult: float,
    fade: bool,
    flag_col: Optional[str] = None,
) -> pd.DataFrame:
    """Enter at first-hour close; walk remaining RTH 5m to SL/TP / 16:00."""
    rows: List[dict] = []
    rest_by = {}
    for day, sess in df5.groupby("session_date", sort=False):
        st = sess["ts"].dt.tz_convert(NY).dt.time
        rest = sess[st >= FH_CLOSE].reset_index(drop=True)
        if not rest.empty:
            rest_by[str(day)] = rest
    for _, sig in fh.iterrows():
        if flag_col is not None and not bool(sig.get(flag_col, False)):
            continue
        candle_side = str(sig["dir"])
        if candle_side not in ("long", "short"):
            continue
        day = str(sig["session_date"])
        rest = rest_by.get(day)
        if rest is None or rest.empty:
            continue
        body = float(sig["body"])
        if body < TICK:
            continue
        if fade:
            side = "short" if candle_side == "long" else "long"
            entry = float(sig["close"])
            sl = 2.0 * float(sig["close"]) - float(sig["open"])
        else:
            side = candle_side
            entry = float(sig["close"])
            sl = float(sig["open"])
        direction = 1 if side == "long" else -1
        tp = entry + direction * float(r_mult) * body
        highs = rest["high"].to_numpy(float)
        lows = rest["low"].to_numpy(float)
        closes = rest["close"].to_numpy(float)
        times = rest["ts"]
        reason = "eod"
        exit_px = float(closes[-1])
        exit_i = len(rest) - 1
        for j in range(len(rest)):
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
                "signal_ts": sig["ts"],
                "exit_ts": times.iloc[exit_i],
                "side": side,
                "candle_side": candle_side,
                "fade": bool(fade),
                "target_r": float(r_mult),
                "flag": flag_col or "is_any",
                "range": float(sig["range"]),
                "body": body,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "exit_px": float(exit_px),
                "reason": reason,
                "r_mult": pts / body,
                "net_usd": net,
                "win": net > 0,
                "hour": 10,
                "year": int(sig["year"]),
                "signal_i": 0,
                "exit_i": int(exit_i),
                "fh_size": sig.get("fh_size"),
                "fh_body": sig.get("fh_body"),
                "fh_close_third": sig.get("fh_close_third"),
                "fh_vs_prior": sig.get("fh_vs_prior"),
                "or15_vs_fh": sig.get("or15_vs_fh"),
                "gap_vs_fh": sig.get("gap_vs_fh"),
            }
        )
    return pd.DataFrame(rows)


def attach_fh_labels(camp: pd.DataFrame, fh: pd.DataFrame) -> pd.DataFrame:
    if camp.empty:
        return camp
    cols = [
        "session_date",
        "fh_size",
        "fh_body",
        "fh_close_third",
        "fh_vs_prior",
        "or15_vs_fh",
        "gap_vs_fh",
        "po_state",
        "po_side",
        "po_outcome",
        "candle_vs_po",
    ]
    have = [c for c in cols if c in fh.columns]
    right = fh[have].drop_duplicates("session_date")
    out = camp.merge(right, on="session_date", how="left", suffixes=("", "_fh"))
    for c in have:
        if c == "session_date":
            continue
        src = c if c in out.columns else c + "_fh"
        if src in out.columns:
            out[c] = out[src]
    return out


def _plot_first_hour(
    sess15: pd.DataFrame,
    trades: pd.DataFrame,
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 7.2))
    x = np.arange(len(sess15))
    o = sess15["open"].to_numpy(float)
    h = sess15["high"].to_numpy(float)
    l = sess15["low"].to_numpy(float)
    c = sess15["close"].to_numpy(float)
    up = c >= o
    times = sess15["ts"]
    for i, ts in enumerate(times):
        if _t(ts) < FH_CLOSE:
            ax.axvspan(i - 0.45, i + 0.45, color="#ffe082", alpha=0.55, zorder=1)
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
    day = str(sess15["session_date"].iloc[0])
    day_tr = trades[trades["session_date"] == day] if trades is not None and not trades.empty else pd.DataFrame()
    # Map first-hour close (~10:25 5m / 10:15 15m) and exit onto 15m index
    ts_list = list(times)
    for _, tr in day_tr.iterrows():
        color = "#1565c0" if tr["side"] == "long" else "#6a1b9a"
        sig = pd.Timestamp(tr["signal_ts"])
        ex = pd.Timestamp(tr["exit_ts"])
        if sig.tzinfo is None:
            sig = sig.tz_localize(NY)
        else:
            sig = sig.tz_convert(NY)
        if ex.tzinfo is None:
            ex = ex.tz_localize(NY)
        else:
            ex = ex.tz_convert(NY)
        si = min(range(len(ts_list)), key=lambda i: abs((pd.Timestamp(ts_list[i]).tz_convert(NY) - sig).total_seconds()))
        ei = min(range(len(ts_list)), key=lambda i: abs((pd.Timestamp(ts_list[i]).tz_convert(NY) - ex).total_seconds()))
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
    ax.set_xlim(-1, len(sess15))
    ax.set_title("NQ first-hour 1h %s  |  gold = 09:30–10:30  |  follow/fade from 10:30 close" % day, fontsize=11)
    ax.set_xlabel("15m bar (09:30 → 16:00)")
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_chart_index(days: Sequence[str], trades: pd.DataFrame, fh: pd.DataFrame) -> None:
    root = HUB / "charts"
    lines = [
        "# NQ first-hour 1h charts",
        "",
        "Full RTH on 15-minute candles. Gold = first hour (09:30–10:30). Markers = follow/fade from 10:30 close.",
        "",
        "| # | Day | fh dir | range | 3R n | 3R net | Chart |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    fh_i = fh.set_index("session_date")
    for i, day in enumerate(days, 1):
        dtr = trades[trades["session_date"] == day] if trades is not None and not trades.empty else pd.DataFrame()
        net = float(dtr["net_usd"].sum()) if not dtr.empty else 0.0
        direction = str(fh_i.loc[day, "dir"]) if day in fh_i.index else ""
        rng = float(fh_i.loc[day, "range"]) if day in fh_i.index else 0.0
        rel = "%s.png" % day
        lines.append(
            "| %d | %s | %s | %.2f | %d | $%.0f | [%s](%s) |"
            % (i, day, direction, rng, len(dtr), net, rel, rel)
        )
    (root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    *,
    email: bool,
    smoke: bool,
    max_charts: int,
    hi: int = 90,
    lo: int = 80,
    output_root: Optional[Path] = None,
) -> None:
    global HUB
    hi_name = pct_name(hi)
    lo_name = pct_name(lo)
    if output_root is not None:
        HUB = Path(output_root)
    elif hi_name != "p90":
        HUB = REPO / "live" / "state" / ("nq_1h_first_hour_ha_%s" % hi_name)
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        _progress("load 5m ...")
        df5 = load_rth_5m(progress=False)
        if smoke:
            dates = df5["session_date"].drop_duplicates()
            keep = set(dates.tail(400))
            df5 = df5[df5["session_date"].isin(keep)].reset_index(drop=True)
            _progress("SMOKE 5m bars=%s" % f"{len(df5):,}")
        _progress("build first-hour candles ...")
        fh = build_first_hour(df5)
        hi_flag = "is_%s" % hi_name
        lo_flag = "is_%s" % lo_name
        n_hi = int(fh[hi_flag].sum()) if hi_flag in fh.columns else 0
        n_lo = int(fh[lo_flag].sum()) if lo_flag in fh.columns else 0
        _progress("  first-hour days=%d %s=%d %s=%d" % (len(fh), hi_name, n_hi, lo_name, n_lo))
        fh.to_csv(HUB / "first_hour_candles.csv", index=False)

        cov_sleeve = pd.DataFrame(
            {
                "session_date": fh["session_date"],
                "has_%s" % hi_name: fh[hi_flag] if hi_flag in fh.columns else False,
                "has_%s" % lo_name: fh[lo_flag] if lo_flag in fh.columns else False,
                "n_%s" % hi_name: fh[hi_flag].astype(int) if hi_flag in fh.columns else 0,
                "n_%s" % lo_name: fh[lo_flag].astype(int) if lo_flag in fh.columns else 0,
                "year": fh["year"],
            }
        )
        flag, sleeve_meta = choose_pct_sleeve(cov_sleeve, hi_name, lo_name)
        _progress("sleeve %s (%s)" % (flag, sleeve_meta["reason"]))

        po = load_po_campaigns(_progress)
        if smoke:
            po = po[po["session_date"].isin(set(fh["session_date"]))].copy()
        fh = attach_po_context(fh, po, p90_col="is_any", progress=_progress)
        large = fh[flag].fillna(False).astype(bool) if flag in fh.columns else fh[hi_flag].fillna(False).astype(bool)
        fh["hp_during_fade_st"] = large & (fh["po_state"] == "during_po") & (fh["candle_vs_po"] == "candle_against_po")
        fh["hp_during_any"] = large & (fh["po_state"] == "during_po")
        fh["hp_after_follow_st"] = large & (fh["po_state"] == "after_po") & (fh["candle_vs_po"] == "candle_against_po")
        fh["hp_after_loss_follow_st"] = fh["hp_after_follow_st"] & (fh["po_outcome"] == "po_loss")
        fh["hp_after_win_fade_st"] = (
            large & (fh["po_state"] == "after_po") & (fh["po_outcome"] == "po_win") & (fh["candle_vs_po"] == "candle_against_po")
        )
        any_ok = fh["is_any"].fillna(False).astype(bool)
        fh["all_during_fade_st"] = any_ok & (fh["po_state"] == "during_po") & (fh["candle_vs_po"] == "candle_against_po")
        fh["all_after_follow_st"] = any_ok & (fh["po_state"] == "after_po") & (fh["candle_vs_po"] == "candle_against_po")
        fh["all_after_loss_follow_st"] = fh["all_after_follow_st"] & (fh["po_outcome"] == "po_loss")
        fh.to_csv(HUB / "first_hour_with_po.csv", index=False)

        books_walk = [
            ("follow_3r_all", "follow 3R all first-hour", "is_any", 3.0, False),
            ("fade_3r_all", "fade 3R all first-hour", "is_any", 3.0, True),
            ("follow_1r_all", "follow 1R all first-hour", "is_any", 1.0, False),
            ("fade_1r_all", "fade 1R all first-hour", "is_any", 1.0, True),
            ("follow_3r_hi", "follow 3R %s first-hour" % hi_name, hi_flag, 3.0, False),
            ("fade_3r_hi", "fade 3R %s first-hour" % hi_name, hi_flag, 3.0, True),
            ("follow_1r_hi", "follow 1R %s first-hour" % hi_name, hi_flag, 1.0, False),
            ("fade_1r_hi", "fade 1R %s first-hour" % hi_name, hi_flag, 1.0, True),
            ("follow_3r_lo", "follow 3R %s first-hour" % lo_name, lo_flag, 3.0, False),
            ("fade_3r_lo", "fade 3R %s first-hour" % lo_name, lo_flag, 3.0, True),
            ("follow_1r_lo", "follow 1R %s first-hour" % lo_name, lo_flag, 1.0, False),
            ("fade_1r_lo", "fade 1R %s first-hour" % lo_name, lo_flag, 1.0, True),
        ]
        hp_walk = [
            ("hp_during_fade_st_3r", "during fade-ST 3R (%s)" % (hi_name if flag == hi_flag else lo_name), "hp_during_fade_st", 3.0, True),
            ("hp_during_fade_st_1r", "during fade-ST 1R (%s)" % (hi_name if flag == hi_flag else lo_name), "hp_during_fade_st", 1.0, True),
            ("all_during_fade_st_3r", "during fade-ST 3R (all)", "all_during_fade_st", 3.0, True),
            ("all_during_fade_st_1r", "during fade-ST 1R (all)", "all_during_fade_st", 1.0, True),
            ("hp_after_follow_st_3r", "after follow-ST 3R (%s)" % (hi_name if flag == hi_flag else lo_name), "hp_after_follow_st", 3.0, False),
            ("hp_after_follow_st_1r", "after follow-ST 1R (%s)" % (hi_name if flag == hi_flag else lo_name), "hp_after_follow_st", 1.0, False),
            ("all_after_loss_follow_st_1r", "after-loss follow-ST 1R (all)", "all_after_loss_follow_st", 1.0, False),
            ("hp_after_win_fade_st_1r", "after-win fade-ST 1R (%s)" % (hi_name if flag == hi_flag else lo_name), "hp_after_win_fade_st", 1.0, True),
        ]

        walked: Dict[str, pd.DataFrame] = {}
        core_sum: List[dict] = []
        hp_sum: List[dict] = []
        for key, label, flag, r, fade in books_walk + hp_walk:
            _progress("walk %s ..." % key)
            tr = walk_first_hour(df5, fh, r_mult=r, fade=fade, flag_col=flag)
            walked[key] = tr
            if not tr.empty:
                tr.to_csv(HUB / ("trades_%s.csv" % key), index=False)
            _progress("  %s n=%d" % (key, len(tr)))
            sc = summarize_book(tr, label)
            if (key, label, flag, r, fade) in books_walk:
                core_sum.append(sc)
            else:
                hp_sum.append(sc)

        mill_keys = [k for k, _, _, _, _ in books_walk[:4]] + ["follow_3r_hi", "fade_3r_hi", "follow_3r_lo", "fade_3r_lo"]
        annotated: Dict[str, pd.DataFrame] = {}
        notables_by_book: Dict[str, List[dict]] = {}
        for key, label, _, _, _ in books_walk:
            if key not in mill_keys:
                continue
            tr = walked[key]
            _progress("annotate %s n=%d ..." % (key, len(tr)))
            camp = trades_to_campaigns(tr, key, FAMILY)
            if camp.empty:
                annotated[key] = camp
                notables_by_book[key] = []
                continue
            camp = annotate_campaigns(camp, "NQ")
            camp = attach_trade_po_labels(camp, fh)
            # first-hour native labels (already on trades; copy if mill dropped them)
            for col in ("fh_size", "fh_body", "fh_close_third", "fh_vs_prior", "or15_vs_fh", "gap_vs_fh"):
                if col in tr.columns and col not in camp.columns:
                    camp[col] = tr[col].values
                elif col in tr.columns:
                    camp[col] = tr[col].values
            camp.to_csv(HUB / ("%s_campaigns.csv" % key), index=False)
            table, _base, notables = profile_frame(camp, FH_CONDS, MIN_N)
            if not table.empty:
                table.to_csv(HUB / ("%s_buckets.csv" % key), index=False)
            annotated[key] = camp
            notables_by_book[key] = notables
            _progress("  notables=%d" % len(notables))

        current_cmp = compare_current_hp(annotated, po_buckets_table())
        if not current_cmp.empty:
            current_cmp.to_csv(HUB / "vs_current_hp.csv", index=False)
        pd.DataFrame(core_sum + hp_sum).to_csv(HUB / "books.csv", index=False)

        # Charts: large first-hour sleeve (chosen hi/lo) follow-3R vs fade-3R by N/S
        fkey = "follow_3r_hi" if flag == hi_flag else "follow_3r_lo"
        dkey = "fade_3r_hi" if flag == hi_flag else "fade_3r_lo"
        f3 = walked[fkey]
        d3 = walked[dkey]
        f3s = summarize_book(f3, "f")
        d3s = summarize_book(d3, "d")
        sleeve_tr = d3 if (d3s.get("ns", -99) > f3s.get("ns", -99)) else f3
        sleeve_name = ("fade 3R %s" if sleeve_tr is d3 else "follow 3R %s") % (
            hi_name if flag == hi_flag else lo_name
        )
        _progress("chart sleeve %s n=%d" % (sleeve_name, len(sleeve_tr)))

        days = choose_chart_days(cov_sleeve, sleeve_tr, flag=flag, max_charts=max_charts)
        df15 = resample_rth(df5, 15)
        by_day = {d: g.reset_index(drop=True) for d, g in df15.groupby("session_date", sort=False)}
        charts_dir = HUB / "charts"
        if charts_dir.exists():
            shutil.rmtree(charts_dir)
        charts_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for i, day in enumerate(days, 1):
            sess = by_day.get(day)
            if sess is None or sess.empty:
                continue
            path = charts_dir / ("%s.png" % day)
            _plot_first_hour(sess, sleeve_tr, path)
            manifest.append({"i": i, "session_date": day, "path": str(path)})
            if i % 25 == 0:
                _progress("  charted %d/%d" % (i, len(days)))
        pd.DataFrame(manifest).to_csv(HUB / "chart_manifest.csv", index=False)
        write_chart_index(days, sleeve_tr, fh)

        write_ha_report(
            HUB,
            title="NQ first-hour 1h follow / fade HA (%s / %s)" % (hi_name, lo_name),
            universe=(
                "Universe: NQ RTH **first hour only** (09:30–10:30 ET), one 1h candle per session. "
                "Entry at 10:30 close; remaining session walked on 5m. "
                "All first hours **and** causal expanding **%s** first-hour range (fallback **%s** if too rare: %s). "
                "Charts: 15m RTH, gold = first hour, sleeve = **%s** (%d charts)."
                % (hi_name, lo_name, sleeve_meta.get("reason", ""), sleeve_name, len(manifest))
            ),
            email_subject="potions: NQ first-hour 1h follow/fade HA complete (%s/%s)" % (hi_name, lo_name),
            core=core_sum,
            hp_sleeves=hp_sum,
            notables_by_book=notables_by_book,
            current_cmp=current_cmp,
            po_n=int(len(po)),
            extra_notes=[
                "First-hour-native conditions: range size (p99/p95/p90/p80), body conviction, close third, vs prior day, OR15 agree/oppose, gap vs first-hour direction.",
                "After-PO sleeves are expected to be thin — most prior-opposed campaigns are still live at 10:30.",
                "Chart index: [`charts/INDEX.md`](charts/INDEX.md).",
            ],
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "smoke": smoke,
                    "po_n": int(len(po)),
                    "first_hour_n": int(len(fh)),
                    "charts": len(manifest),
                    "chart_sleeve": sleeve_name,
                    "hi": hi_name,
                    "lo": lo_name,
                    "flag": flag,
                    "sleeve": sleeve_meta,
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
            "potions: NQ first-hour 1h HA FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ first-hour 1h HA FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ first-hour 1h follow/fade HA complete (%s/%s)" % (hi_name, lo_name),
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-charts", type=int, default=MAX_CHARTS_DEFAULT)
    ap.add_argument("--hi", type=int, default=90, help="Primary first-hour percentile (90 or 99)")
    ap.add_argument("--lo", type=int, default=80, help="Fallback percentile if hi is too rare")
    ap.add_argument("--output-root", type=Path, default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        max_charts=int(args.max_charts),
        hi=int(args.hi),
        lo=int(args.lo),
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
