"""Heikin Ashi overlay on prior-opposed books + post-exit continuation.

Diagnostic only — not a promotion gate.

Questions:
  1. At prior-opposed entry, does causal 5m HA agree with the fade (counter-trend)
     or still point with the implied prior ST (trend continuation)?
  2. How do those HA buckets compare with the current HP condition shortlist
     (OR-norm, ST-age, RSI-against, 5m MA)?
  3. After the prior-opposed campaign exits, does a 3R follow of HA / implied-ST
     (trend continuation) beat another fade in the PO direction?

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.prior_opposed_ha_study --email
  python -m live.prior_opposed_ha_study --email --smoke
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .futures_intraday_hp_sizeup_lib import (
    POINT_VALUES,
    book_by_key,
    ensure_tf_bars,
)
from .notify_email import send_email

def load_5m_bars(symbol: str) -> pd.DataFrame:
    """Prefer NQ RTH CSV; otherwise cached/resampled 5m."""
    if symbol.upper() in ("NQ", "MNQ"):
        p = REPO / "nq" / "nq_5min_rth.csv"
        if p.exists():
            raw = pd.read_csv(p)
            ts = pd.to_datetime(raw["ts_event"], utc=True, errors="coerce")
            if ts.isna().any():
                ts = pd.to_datetime(raw["ts_event"], errors="coerce")
                if getattr(ts.dt, "tz", None) is None:
                    ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
                else:
                    ts = ts.dt.tz_convert(NY)
            else:
                ts = ts.dt.tz_convert(NY)
            df = pd.DataFrame(
                {
                    "ts": ts,
                    "open": pd.to_numeric(raw["open"], errors="coerce"),
                    "high": pd.to_numeric(raw["high"], errors="coerce"),
                    "low": pd.to_numeric(raw["low"], errors="coerce"),
                    "close": pd.to_numeric(raw["close"], errors="coerce"),
                    "volume": pd.to_numeric(raw["volume"], errors="coerce").fillna(0.0)
                    if "volume" in raw.columns
                    else 0.0,
                }
            ).dropna(subset=["ts", "open", "high", "low", "close"])
            return df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)
    df = ensure_tf_bars(symbol, "5m")
    if df is None or df.empty:
        return pd.DataFrame()
    return df.sort_values("ts").reset_index(drop=True)
HUB = REPO / "live" / "state" / "prior_opposed_ha"
PROFILE_HUB = REPO / "live" / "state" / "futures_intraday_condition_profile"
NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
FEE = 1.50
CUTOFF_CONT = time(15, 30)
HA_SHIFT = pd.Timedelta(minutes=5)

BOOKS = (
    "nq_prior_opposed_rl",
    "ym_prior_opposed_rl",
)

CURRENT_CONDS = (
    ("or15_width_pct", "Opening 15m range vs ATR"),
    ("st_age_bucket", "ST-event age"),
    ("rsi_align", "Hourly RSI vs trade"),
    ("ma5_align", "5m MA vs trade"),
    ("or15_dir_align", "Opening 15m direction vs trade"),
    ("on_third", "Overnight range third"),
)

MIN_N = 40


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def score_nets(nets: np.ndarray) -> Dict[str, float]:
    nets = np.asarray(nets, dtype=float)
    if nets.size == 0:
        return {"n": 0, "net": 0.0, "stress": 0.0, "ns": 0.0, "wr": 0.0, "avg": 0.0}
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    stress = float(abs((eq - peak).min()))
    net = float(nets.sum())
    return {
        "n": int(nets.size),
        "net": net,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
        "wr": float((nets > 0).mean()),
        "avg": float(nets.mean()),
        "wins": int((nets > 0).sum()),
    }


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Causal sequential HA from regular OHLC."""
    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    ha_c = (o + h + l + c) / 4.0
    ha_o = np.empty_like(ha_c)
    ha_o[0] = 0.5 * (o[0] + c[0])
    for i in range(1, ha_o.size):
        ha_o[i] = 0.5 * (ha_o[i - 1] + ha_c[i - 1])
    out = df.copy()
    out["ha_open"] = ha_o
    out["ha_close"] = ha_c
    out["ha_high"] = np.maximum.reduce([h, ha_o, ha_c])
    out["ha_low"] = np.minimum.reduce([l, ha_o, ha_c])
    out["ha_bull"] = ha_c >= ha_o
    bull = out["ha_bull"].to_numpy()
    streak = np.ones(bull.size, dtype=int)
    for i in range(1, bull.size):
        if bull[i] == bull[i - 1]:
            streak[i] = streak[i - 1] + 1
    out["ha_streak"] = streak
    return out


def _ha_feat_frame(bars: pd.DataFrame) -> pd.DataFrame:
    ha = heikin_ashi(bars)
    feat = pd.DataFrame(
        {
            "ts": ha["ts"] + HA_SHIFT,
            "ha_bull": ha["ha_bull"].to_numpy(),
            "ha_open": ha["ha_open"].to_numpy(),
            "ha_close": ha["ha_close"].to_numpy(),
            "ha_streak": ha["ha_streak"].to_numpy(),
        }
    )
    feat["ha_color"] = np.where(feat["ha_bull"], "ha_bull", "ha_bear")
    return feat.sort_values("ts")


def attach_ha(camp: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    feat = _ha_feat_frame(bars)
    left = camp.sort_values("entry_ts").copy()
    merged = pd.merge_asof(
        left,
        feat,
        left_on="entry_ts",
        right_on="ts",
        direction="backward",
    )
    out = camp.copy()
    for col in ("ha_color", "ha_bull", "ha_streak", "ha_open", "ha_close"):
        out[col] = merged[col].values
    bull = out["ha_bull"].fillna(False).astype(bool)
    ha_na = out["ha_color"].isna()
    out["ha_vs_po"] = np.where(
        ha_na,
        "ha_na",
        np.where(
            ((out["side"] == "long") & bull) | ((out["side"] == "short") & ~bull),
            "ha_with_fade",
            "ha_with_prior_trend",
        ),
    )
    # Implied ST = opposite of prior-opposed trade (by construction).
    out["implied_st"] = np.where(out["side"] == "long", "short", "long")
    out["ha_vs_st"] = np.where(
        ha_na,
        "ha_na",
        np.where(
            ((out["implied_st"] == "long") & bull) | ((out["implied_st"] == "short") & ~bull),
            "ha_confirms_st",
            "ha_fades_st",
        ),
    )
    out["ha_streak_bucket"] = np.where(
        out["ha_streak"].isna(),
        "streak_na",
        np.where(
            out["ha_streak"] <= 2,
            "streak_1_2",
            np.where(out["ha_streak"] <= 6, "streak_3_6", "streak_ge7"),
        ),
    )
    return out


def bucket_table(df: pd.DataFrame, col: str, title: str, baseline: Dict[str, float]) -> pd.DataFrame:
    rows = []
    p0 = baseline["wr"]
    n0 = max(baseline["n"], 1)
    for val, g in df.groupby(col, dropna=False):
        sc = score_nets(g["net_usd"].to_numpy(float))
        if sc["n"] < 1:
            continue
        se = math.sqrt(max(p0 * (1 - p0) * (1 / sc["n"] + 1 / n0), 1e-12))
        z = (sc["wr"] - p0) / se if se > 0 else 0.0
        rows.append(
            {
                "condition": title,
                "bucket": str(val),
                "n": sc["n"],
                "wins": sc["wins"],
                "wr": sc["wr"],
                "avg_net": sc["avg"],
                "net": sc["net"],
                "stress": sc["stress"],
                "ns": sc["ns"],
                "wr_lift_pp": 100.0 * (sc["wr"] - p0),
                "avg_lift": sc["avg"] - baseline["avg"],
                "z_wr": z,
                "coverage": sc["n"] / n0,
            }
        )
    return pd.DataFrame(rows).sort_values(["z_wr", "n"], ascending=False)


def cross_ha_current(df: pd.DataFrame, baseline: Dict[str, float]) -> pd.DataFrame:
    rows = []
    p0 = baseline["wr"]
    n0 = max(baseline["n"], 1)
    for cond, title in CURRENT_CONDS:
        if cond not in df.columns:
            continue
        for (ha, cur), g in df.groupby(["ha_vs_po", cond], dropna=False):
            sc = score_nets(g["net_usd"].to_numpy(float))
            if sc["n"] < MIN_N:
                continue
            se = math.sqrt(max(p0 * (1 - p0) * (1 / sc["n"] + 1 / n0), 1e-12))
            z = (sc["wr"] - p0) / se if se > 0 else 0.0
            rows.append(
                {
                    "ha_vs_po": str(ha),
                    "current_condition": title,
                    "current_bucket": str(cur),
                    "n": sc["n"],
                    "wr": sc["wr"],
                    "avg_net": sc["avg"],
                    "net": sc["net"],
                    "ns": sc["ns"],
                    "wr_lift_pp": 100.0 * (sc["wr"] - p0),
                    "z_wr": z,
                    "coverage": sc["n"] / n0,
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["z_wr", "n"], ascending=False)


def _rth_session(bars: pd.DataFrame, day) -> pd.DataFrame:
    d = bars[(bars["ts"].dt.date == day)].copy()
    if d.empty:
        return d
    t = d["ts"].dt.time
    return d[(t >= RTH_OPEN) & (t < RTH_CLOSE)].sort_values("ts")


def walk_3r(
    sess: pd.DataFrame,
    *,
    start_ts: pd.Timestamp,
    side: str,
    pv: float,
) -> Optional[dict]:
    """Enter at first 5m close after start_ts; SL at that bar's open; TP=3R; EOD flatten."""
    after = sess[sess["ts"] >= start_ts]
    if after.empty:
        return None
    sig = after.iloc[0]
    if pd.Timestamp(sig["ts"]).time() >= CUTOFF_CONT:
        return None
    o = float(sig["open"])
    c = float(sig["close"])
    body = abs(c - o)
    if body < 1.0:
        return None
    direction = 1 if side == "long" else -1
    entry = c
    sl = o
    r = body
    tp = entry + direction * 3.0 * r
    rest = after.iloc[1:]
    exit_px = float("nan")
    reason = "eod"
    exit_ts = sess.iloc[-1]["ts"]
    for _, bar in rest.iterrows():
        hi = float(bar["high"])
        lo = float(bar["low"])
        hit_sl = lo <= sl if side == "long" else hi >= sl
        hit_tp = hi >= tp if side == "long" else lo <= tp
        if hit_sl and hit_tp:
            exit_px, reason, exit_ts = sl, "stop", bar["ts"]
            break
        if hit_sl:
            exit_px, reason, exit_ts = sl, "stop", bar["ts"]
            break
        if hit_tp:
            exit_px, reason, exit_ts = tp, "target", bar["ts"]
            break
    if reason == "eod":
        exit_px = float(sess.iloc[-1]["close"])
    pts = (exit_px - entry) * direction
    net = pts * pv - FEE
    r_mult = pts / r if r > 0 else 0.0
    return {
        "entry_ts": sig["ts"],
        "exit_ts": exit_ts,
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "exit_px": exit_px,
        "reason": reason,
        "net_usd": net,
        "r_mult": r_mult,
        "win": net > 0,
    }


def continuation_book(camp: pd.DataFrame, bars: pd.DataFrame, pv: float) -> pd.DataFrame:
    by_date: Dict = {d: g for d, g in bars.groupby(bars["ts"].dt.date, sort=False)}
    rows = []
    for _, row in camp.iterrows():
        day = pd.Timestamp(row["entry_ts"]).date()
        sess = by_date.get(day)
        if sess is None or sess.empty:
            t = bars["ts"].dt.time
            sess = bars[
                (bars["ts"].dt.date == day) & (t >= RTH_OPEN) & (t < RTH_CLOSE)
            ]
        if sess is None or sess.empty:
            continue
        sess = sess.sort_values("ts")
        exit_ts = pd.Timestamp(row["exit_ts"])
        fade_side = str(row["side"])
        st_side = "short" if fade_side == "long" else "long"
        ha_side = "long" if bool(row.get("ha_bull")) else "short"
        after = sess[sess["ts"] >= (exit_ts + pd.Timedelta(minutes=1))]
        if after.empty:
            continue
        sig = after.iloc[0]
        sig_side = "long" if float(sig["close"]) > float(sig["open"]) else (
            "short" if float(sig["close"]) < float(sig["open"]) else ""
        )
        if not sig_side:
            continue
        for label, side in (
            ("trend_continuation_st", st_side),
            ("countertrend_again_po", fade_side),
            ("follow_ha_at_entry", ha_side),
        ):
            if side != sig_side:
                continue
            tr = walk_3r(sess, start_ts=exit_ts + pd.Timedelta(minutes=1), side=side, pv=pv)
            if tr is None:
                continue
            rec = dict(tr)
            rec["book"] = row["book"]
            rec["symbol"] = row["symbol"]
            rec["session_date"] = str(day)
            rec["po_trade_id"] = row["trade_id"]
            rec["sleeve"] = label
            rec["po_side"] = fade_side
            rec["ha_vs_po"] = row.get("ha_vs_po")
            rec["po_net"] = float(row["net_usd"])
            rec["po_win"] = bool(row["win"])
            rows.append(rec)
    return pd.DataFrame(rows)


def load_campaign_csv(key: str) -> pd.DataFrame:
    path = PROFILE_HUB / ("%s_campaigns.csv" % key)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert(NY)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert(NY)
    df["net_usd"] = pd.to_numeric(df["net_usd"], errors="coerce")
    df["win"] = df["net_usd"] > 0
    return df


def _md_bucket_table(tbl: pd.DataFrame, n: int = 12) -> List[str]:
    if tbl is None or tbl.empty:
        return ["_(empty)_", ""]
    cols = [c for c in ("condition", "bucket", "n", "wr", "avg_net", "net", "ns", "wr_lift_pp", "z_wr") if c in tbl.columns]
    show = tbl.head(n)
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "|".join("---:" if c not in ("condition", "bucket") else "---" for c in cols) + "|",
    ]
    for _, r in show.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c in ("wr",):
                cells.append("%.1f%%" % (100.0 * float(v)))
            elif c in ("avg_net", "net", "ns", "wr_lift_pp", "z_wr"):
                cells.append("%.2f" % float(v))
            elif c == "n":
                cells.append("%d" % int(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def write_report(
    *,
    annotated: Dict[str, pd.DataFrame],
    ha_tables: Dict[str, pd.DataFrame],
    crosses: Dict[str, pd.DataFrame],
    cont: pd.DataFrame,
) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Prior-opposed Heikin Ashi overlay",
        "",
        "Diagnostic. Causal 5m HA (bar must complete before entry). "
        "Prior-opposed trades are **counter-trend vs implied ST** by construction "
        "(implied ST = opposite of the PO side).",
        "",
        "- **ha_with_fade** — HA color agrees with the prior-opposed trade (HA also fading ST).",
        "- **ha_with_prior_trend** — HA still points with implied ST (trend-continuation pressure vs the fade).",
        "",
        "Current-condition columns are the existing futures HP profile (OR-norm, ST-age, RSI, 5m MA).",
        "",
    ]
    email = [
        "potions: prior-opposed HA overlay complete",
        "",
        "Hub: %s" % HUB.resolve(),
        "",
    ]
    for key, df in annotated.items():
        base = score_nets(df["net_usd"].to_numpy(float))
        lines += [
            "## %s" % key,
            "",
            "Baseline n=%d WR=%.1f%% net=$%.0f N/S=%.2f" % (base["n"], 100 * base["wr"], base["net"], base["ns"]),
            "",
        ]
        email.append(
            "%s  n=%d WR=%.0f%% net=$%.0f N/S=%.2f"
            % (key, base["n"], 100 * base["wr"], base["net"], base["ns"])
        )
        tbl = ha_tables.get(key)
        if tbl is not None and not tbl.empty:
            fade = tbl[(tbl["condition"] == "HA vs prior-opposed") & (tbl["bucket"] == "ha_with_fade")]
            trend = tbl[(tbl["condition"] == "HA vs prior-opposed") & (tbl["bucket"] == "ha_with_prior_trend")]
            lines += ["### HA vs PO / ST", ""] + _md_bucket_table(tbl, 20)
            if not fade.empty and not trend.empty:
                f, t = fade.iloc[0], trend.iloc[0]
                stance = (
                    "HA-with-fade looks **better** than HA-with-prior-trend"
                    if float(f["avg_net"]) > float(t["avg_net"])
                    else "HA-with-prior-trend looks **better** than HA-with-fade (fade is fighting HA)"
                )
                lines.append(
                    "Read: fade n=%d WR=%.1f%% avg=$%.0f vs trend-HA n=%d WR=%.1f%% avg=$%.0f. %s."
                    % (
                        int(f["n"]),
                        100 * float(f["wr"]),
                        float(f["avg_net"]),
                        int(t["n"]),
                        100 * float(t["wr"]),
                        float(t["avg_net"]),
                        stance,
                    )
                )
                lines.append("")
                email.append(
                    "  fade HA n=%d WR=%.0f%% avg=$%.0f | trend HA n=%d WR=%.0f%% avg=$%.0f"
                    % (
                        int(f["n"]),
                        100 * float(f["wr"]),
                        float(f["avg_net"]),
                        int(t["n"]),
                        100 * float(t["wr"]),
                        float(t["avg_net"]),
                    )
                )
        cr = crosses.get(key)
        if cr is not None and not cr.empty:
            lines += ["### HA × current HP conditions (n≥%d)" % MIN_N, ""]
            show_cols = ["ha_vs_po", "current_condition", "current_bucket", "n", "wr", "avg_net", "ns", "z_wr"]
            head = cr.head(15)
            lines.append("| " + " | ".join(show_cols) + " |")
            lines.append("|" + "|".join("---:" if c not in ("ha_vs_po", "current_condition", "current_bucket") else "---" for c in show_cols) + "|")
            for _, r in head.iterrows():
                lines.append(
                    "| %s | %s | %s | %d | %.1f%% | %.0f | %.2f | %.2f |"
                    % (
                        r["ha_vs_po"],
                        r["current_condition"],
                        r["current_bucket"],
                        int(r["n"]),
                        100 * float(r["wr"]),
                        float(r["avg_net"]),
                        float(r["ns"]),
                        float(r["z_wr"]),
                    )
                )
            lines.append("")
            top = cr.iloc[0]
            email.append(
                "  best cross: %s × %s=%s n=%d WR=%.0f%% z=%.1f"
                % (
                    top["ha_vs_po"],
                    top["current_condition"],
                    top["current_bucket"],
                    int(top["n"]),
                    100 * float(top["wr"]),
                    float(top["z_wr"]),
                )
            )

    lines += [
        "## Post-exit 3R (after PO campaign)",
        "",
        "First 5m close after PO exit; SL at that candle open; TP 3× body; flatten 16:00. "
        "Skip if exit ≥ 15:30. Conservative same-bar: stop before target.",
        "",
        "| Sleeve | n | WR | avg | net | N/S | PF-proxy |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    email.append("")
    email.append("Post-exit 3R:")
    if cont is not None and not cont.empty:
        for sleeve, g in cont.groupby("sleeve"):
            sc = score_nets(g["net_usd"].to_numpy(float))
            wins = g.loc[g["net_usd"] > 0, "net_usd"].sum()
            losses = g.loc[g["net_usd"] <= 0, "net_usd"].sum()
            pf = abs(wins / losses) if losses < 0 else 99.0
            lines.append(
                "| %s | %d | %.1f%% | $%.0f | $%.0f | %.2f | %.2f |"
                % (sleeve, sc["n"], 100 * sc["wr"], sc["avg"], sc["net"], sc["ns"], pf)
            )
            email.append(
                "  %s n=%d WR=%.0f%% net=$%.0f N/S=%.2f"
                % (sleeve, sc["n"], 100 * sc["wr"], sc["net"], sc["ns"])
            )
        lines.append("")
        # Per book
        lines += [
            "### By book",
            "",
            "| Book | Sleeve | n | WR | net | N/S |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for (bk, sl), g in cont.groupby(["book", "sleeve"]):
            sc = score_nets(g["net_usd"].to_numpy(float))
            lines.append(
                "| %s | %s | %d | %.1f%% | $%.0f | %.2f |"
                % (bk, sl, sc["n"], 100 * sc["wr"], sc["net"], sc["ns"])
            )
        lines.append("")
    else:
        lines.append("_(no continuation trades)_")
        lines.append("")

    lines += [
        "## Stance",
        "",
        "Research curiosity only. Do **not** promote an HA filter from this pass. "
        "Compare HA lift to the already-shortlisted HP buckets (NQ OR-norm is the live HP candidate). "
        "Post-exit 3R is a separate satellite idea — needs nulls before any size.",
        "",
        "Hub: `%s`" % HUB.resolve(),
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run(*, books: Sequence[str], email: bool, smoke: bool) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    annotated: Dict[str, pd.DataFrame] = {}
    ha_tables: Dict[str, pd.DataFrame] = {}
    crosses: Dict[str, pd.DataFrame] = {}
    cont_frames: List[pd.DataFrame] = []
    bar_cache: Dict[str, pd.DataFrame] = {}

    try:
        for key in books:
            _progress("BOOK %s" % key)
            spec = book_by_key(key)
            camp = load_campaign_csv(key)
            if smoke:
                camp = camp.head(80).copy()
            _progress("  campaigns=%d" % len(camp))
            if spec.symbol not in bar_cache:
                _progress("  load 5m %s" % spec.symbol)
                raw = load_5m_bars(spec.symbol)
                if raw is None or raw.empty:
                    _progress("  SKIP no 5m")
                    continue
                bar_cache[spec.symbol] = raw
                _progress("  bars=%s" % f"{len(bar_cache[spec.symbol]):,}")
            bars = bar_cache[spec.symbol]
            ann = attach_ha(camp, bars)
            ann.to_csv(HUB / ("%s_campaigns_ha.csv" % key), index=False)
            annotated[key] = ann
            base = score_nets(ann["net_usd"].to_numpy(float))
            parts = [
                bucket_table(ann, "ha_vs_po", "HA vs prior-opposed", base),
                bucket_table(ann, "ha_vs_st", "HA vs implied ST", base),
                bucket_table(ann, "ha_color", "HA color", base),
                bucket_table(ann, "ha_streak_bucket", "HA streak", base),
            ]
            tbl = pd.concat([p for p in parts if p is not None and not p.empty], ignore_index=True)
            tbl.insert(0, "book", key)
            tbl.to_csv(HUB / ("%s_ha_buckets.csv" % key), index=False)
            ha_tables[key] = tbl
            cr = cross_ha_current(ann, base)
            if not cr.empty:
                cr.insert(0, "book", key)
                cr.to_csv(HUB / ("%s_ha_x_current.csv" % key), index=False)
            crosses[key] = cr
            pv = float(POINT_VALUES.get(spec.symbol.upper(), 20.0))
            _progress("  continuation 3R ...")
            cont = continuation_book(ann, bars, pv)
            if not cont.empty:
                cont_frames.append(cont)
                _progress("  continuation trades=%d" % len(cont))

        all_ann = pd.concat(annotated.values(), ignore_index=True) if annotated else pd.DataFrame()
        if not all_ann.empty:
            all_ann.to_csv(HUB / "all_campaigns_ha.csv", index=False)
        all_tbl = pd.concat(ha_tables.values(), ignore_index=True) if ha_tables else pd.DataFrame()
        if not all_tbl.empty:
            all_tbl.to_csv(HUB / "ha_buckets.csv", index=False)
        all_cr = pd.concat([c for c in crosses.values() if c is not None and not c.empty], ignore_index=True) if crosses else pd.DataFrame()
        if not all_cr.empty:
            all_cr.to_csv(HUB / "ha_x_current.csv", index=False)
        cont = pd.concat(cont_frames, ignore_index=True) if cont_frames else pd.DataFrame()
        if not cont.empty:
            cont.to_csv(HUB / "post_exit_3r.csv", index=False)

        write_report(annotated=annotated, ha_tables=ha_tables, crosses=crosses, cont=cont)
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "books": list(books), "smoke": smoke}, indent=2) + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: prior-opposed HA overlay FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: prior-opposed HA overlay FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: prior-opposed HA overlay complete",
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", action="append", default=None)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    keys = args.book or (["nq_prior_opposed_rl"] if args.smoke else list(BOOKS))
    run(books=keys, email=bool(args.email), smoke=bool(args.smoke))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
