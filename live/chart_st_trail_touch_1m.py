"""Chart 1m RTH sessions for days that approached/touched the 1h ST trail.

Sources:
  NQ  — ``live/state/nq_1h_first_hour_broker_sweep_trail/``
  NAS — ``live/state/futures_intraday_hp_nas100_nq_lead/trail_gate/``

Touch day = any approach / bounce / aggressive_bounce / hit_bar event
(price within 8 pts of the live ST trail stop, or traded through it).
"""

from __future__ import annotations

import argparse
import json
from datetime import date, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

NY = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
TOUCH_EVENTS = {"approach", "bounce", "aggressive_bounce", "hit_bar"}
SLUG = "follow_3r_strong_sweep_st_trail"

HUBS = {
    "NQ": REPO / "live" / "state" / "nq_1h_first_hour_broker_sweep_trail",
    "NAS100": REPO / "live" / "state" / "futures_intraday_hp_nas100_nq_lead" / "trail_gate",
}
OUT_SUBDIR = "trail_touch_1m_charts"


def _progress(msg: str) -> None:
    print(msg.rstrip(), flush=True)


def load_events(hub: Path) -> pd.DataFrame:
    path = hub / ("%s_trail_events.jsonl" % SLUG)
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return pd.DataFrame(rows)


def touch_days(events: pd.DataFrame) -> List[str]:
    if events.empty:
        return []
    mask = events["event"].astype(str).isin(TOUCH_EVENTS)
    days = sorted(events.loc[mask, "session_date"].astype(str).unique())
    return days


def load_nq_1m_days(days: Sequence[str]) -> Dict[str, pd.DataFrame]:
    from .futures_intraday_hp_sizeup_lib import DBN_1M
    from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

    path = DBN_1M["NQ"]
    _progress("loading NQ 1m DBN (filter %d days) ..." % len(days))
    by_day = load_1m_by_ny_date_any(path.resolve(), "nq")
    out: Dict[str, pd.DataFrame] = {}
    want = set(days)
    for d, frame in by_day.items():
        key = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        if key not in want:
            continue
        df = frame.reset_index().rename(columns={"ts_event": "ts", "index": "ts"})
        if "ts" not in df.columns:
            df = frame.copy()
            df["ts"] = df.index
            df = df.reset_index(drop=True)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        st = df["ts"].dt.time
        df = df[(st >= RTH_OPEN) & (st < RTH_CLOSE)].dropna(subset=["open", "high", "low", "close"])
        out[key] = df.sort_values("ts").reset_index(drop=True)
    return out


def load_nas_1m_days(days: Sequence[str]) -> Dict[str, pd.DataFrame]:
    path = REPO / "fx" / "nas100_1m.csv"
    want = set(days)
    _progress("loading NAS100 1m CSV for %d days ..." % len(days))
    # Stream filter — file is ~184MB.
    chunks: List[pd.DataFrame] = []
    usecols = None
    for chunk in pd.read_csv(path, chunksize=200_000):
        if usecols is None:
            usecols = list(chunk.columns)
        ts_col = "ts_event" if "ts_event" in chunk.columns else "ts"
        ts = pd.to_datetime(chunk[ts_col], utc=True, errors="coerce")
        if ts.isna().all():
            ts = pd.to_datetime(chunk[ts_col], errors="coerce")
            if getattr(ts.dt, "tz", None) is None:
                ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
            else:
                ts = ts.dt.tz_convert(NY)
        else:
            ts = ts.dt.tz_convert(NY)
        chunk = chunk.assign(ts=ts).dropna(subset=["ts"])
        chunk["session_date"] = chunk["ts"].dt.strftime("%Y-%m-%d")
        sub = chunk[chunk["session_date"].isin(want)]
        if not sub.empty:
            chunks.append(sub)
    if not chunks:
        return {}
    df = pd.concat(chunks, ignore_index=True)
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    st = df["ts"].dt.time
    df = df[(st >= RTH_OPEN) & (st < RTH_CLOSE)].dropna(subset=["open", "high", "low", "close"])
    out: Dict[str, pd.DataFrame] = {}
    for day, g in df.groupby("session_date", sort=True):
        out[str(day)] = g.sort_values("ts").reset_index(drop=True)
    return out


def _trail_step_series(day_ev: pd.DataFrame, sess: pd.DataFrame) -> tuple:
    """Step-forward trail from trail_modify (+ approach trail values) onto 1m index."""
    mods = day_ev[day_ev["event"].astype(str).isin(["trail_modify", "approach", "bounce", "aggressive_bounce", "hit_bar"])].copy()
    if mods.empty or sess.empty:
        return [], []
    mods["ts"] = pd.to_datetime(mods["ts"])
    # naive NY wall clock for events written as YYYY-MM-DDTHH:MM:SS
    if mods["ts"].dt.tz is None:
        mods["ts"] = mods["ts"].dt.tz_localize(NY)
    else:
        mods["ts"] = mods["ts"].dt.tz_convert(NY)
    px_col = "stop_price" if "stop_price" in mods.columns else "trail"
    if "trail" in mods.columns:
        mods["lvl"] = pd.to_numeric(mods["trail"], errors="coerce").fillna(pd.to_numeric(mods.get(px_col), errors="coerce"))
    else:
        mods["lvl"] = pd.to_numeric(mods.get(px_col), errors="coerce")
    mods = mods.dropna(subset=["lvl"]).sort_values("ts")
    ts_arr = sess["ts"].to_numpy()
    xs: List[int] = []
    ys: List[float] = []
    mi = 0
    cur = None
    mod_ts = mods["ts"].to_numpy()
    mod_lvl = mods["lvl"].to_numpy(float)
    for i, ts in enumerate(ts_arr):
        t = pd.Timestamp(ts)
        while mi < len(mod_ts) and pd.Timestamp(mod_ts[mi]) <= t:
            cur = float(mod_lvl[mi])
            mi += 1
        if cur is not None:
            xs.append(i)
            ys.append(cur)
    return xs, ys


def plot_day(
    *,
    instrument: str,
    day: str,
    sess: pd.DataFrame,
    day_ev: pd.DataFrame,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(18, 7.2))
    x = np.arange(len(sess))
    o = sess["open"].to_numpy(float)
    h = sess["high"].to_numpy(float)
    l = sess["low"].to_numpy(float)
    c = sess["close"].to_numpy(float)
    up = c >= o
    ax.vlines(x, l, h, color=np.where(up, "#2e7d32", "#c62828"), linewidth=0.55, zorder=3)
    body_h = np.maximum(np.abs(c - o), (h.max() - l.min()) * 0.0008)
    for xi, oi, ci, uu in zip(x, o, c, up):
        ax.add_patch(
            plt.Rectangle(
                (xi - 0.35, min(oi, ci)),
                0.7,
                body_h[int(xi)],
                facecolor="#2e7d32" if uu else "#c62828",
                edgecolor="#1b5e20" if uu else "#8e0000",
                linewidth=0.2,
                zorder=4,
            )
        )
    xs, ys = _trail_step_series(day_ev, sess)
    if xs:
        ax.plot(xs, ys, color="#ff6f00", lw=1.5, label="1h ST trail stop", zorder=6)

    ts_list = list(sess["ts"])
    colors = {
        "approach": "#1565c0",
        "bounce": "#6a1b9a",
        "aggressive_bounce": "#c62828",
        "hit_bar": "#000000",
    }
    for ev_name, color in colors.items():
        sub = day_ev[day_ev["event"].astype(str) == ev_name]
        if sub.empty:
            continue
        for _, r in sub.iterrows():
            ts = pd.Timestamp(r["ts"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(NY)
            else:
                ts = ts.tz_convert(NY)
            idx = int(np.argmin([abs((pd.Timestamp(t) - ts).total_seconds()) for t in ts_list]))
            px = r.get("close")
            if px is None or (isinstance(px, float) and not np.isfinite(px)):
                px = r.get("trail") or r.get("stop_price")
            ax.scatter([idx], [float(px)], c=color, s=42 if ev_name != "approach" else 28, zorder=8, label=ev_name)

    # hour grid labels every 30m
    labels = []
    ticks = []
    for i, ts in enumerate(ts_list):
        t = pd.Timestamp(ts).tz_convert(NY)
        if t.minute in (0, 30):
            ticks.append(i)
            labels.append(t.strftime("%H:%M"))
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    n_touch = int(day_ev["event"].astype(str).isin(TOUCH_EVENTS).sum())
    ax.set_title("%s %s  |  1m RTH  |  ST-trail touch/approach events=%d" % (instrument, day, n_touch))
    ax.grid(True, alpha=0.22)
    handles, labs = ax.get_legend_handles_labels()
    uniq = dict(zip(labs, handles))
    if uniq:
        ax.legend(uniq.values(), uniq.keys(), loc="best", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def chart_instrument(instrument: str, hub: Path) -> dict:
    events = load_events(hub)
    days = touch_days(events)
    out_dir = hub / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    _progress("%s touch days=%d → %s" % (instrument, len(days), out_dir))
    if not days:
        return {"instrument": instrument, "n_days": 0, "n_charts": 0, "out_dir": str(out_dir)}

    if instrument == "NQ":
        by_day = load_nq_1m_days(days)
    else:
        by_day = load_nas_1m_days(days)

    written = 0
    missing = []
    for day in days:
        sess = by_day.get(day)
        if sess is None or sess.empty:
            missing.append(day)
            continue
        day_ev = events[events["session_date"].astype(str) == day]
        plot_day(
            instrument=instrument,
            day=day,
            sess=sess,
            day_ev=day_ev,
            out_path=out_dir / ("%s.png" % day),
        )
        written += 1
        _progress("  wrote %s/%s.png" % (OUT_SUBDIR, day))

    lines = [
        "# %s 1m ST-trail touch charts" % instrument,
        "",
        "Days with approach / bounce / aggressive_bounce / hit_bar vs the live 1h ATR SuperTrend trail stop.",
        "Orange = trail stop (stepped from trail_modify + touch events). Markers = touch events.",
        "Tape: NY RTH 09:30–16:00 on **1-minute** bars.",
        "",
        "| Day | Events | Chart |",
        "|---|---:|---|",
    ]
    for day in days:
        n = int(
            (
                (events["session_date"].astype(str) == day)
                & (events["event"].astype(str).isin(TOUCH_EVENTS))
            ).sum()
        )
        chart = "%s.png" % day if day not in missing else "(missing 1m)"
        lines.append("| %s | %d | %s |" % (day, n, chart))
    if missing:
        lines += ["", "## Missing 1m", "", *[("- %s" % d) for d in missing]]
    lines += ["", "%d charts written under `%s/`." % (written, OUT_SUBDIR), ""]
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "instrument": instrument,
        "n_days": len(days),
        "n_charts": written,
        "missing": missing,
        "out_dir": str(out_dir),
        "days": days,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markets", default="NQ,NAS100")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)

    results = []
    for m in [x.strip().upper() for x in args.markets.split(",") if x.strip()]:
        if m not in HUBS:
            raise SystemExit("unknown market %s" % m)
        results.append(chart_instrument(m, HUBS[m]))

    body = ["ST-trail touch 1m charts complete", ""]
    for r in results:
        body.append(
            "%s: days=%d charts=%d → %s"
            % (r["instrument"], r["n_days"], r["n_charts"], r["out_dir"])
        )
        if r.get("missing"):
            body.append("  missing 1m: %s" % ", ".join(r["missing"]))
    body.append("")
    text = "\n".join(body)
    print(text)
    if args.email:
        send_email(subject="potions: ST-trail touch 1m charts complete", body=text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
