"""Asia-range London session charts (Asia OR window + London trade window).

Writes ``<output_root>/charts/usdjpy_asia_range_session_YYYY-MM-DD.png`` for each
session that has bars spanning the overnight Asia OR (19:00–03:00 NY) through
London EOD (~11:59 NY). Annotates campaign-parity decision (skip/pf, sitout, …).

Usage:
  PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \\
    python -m live.demo.asia_range_session_charts \\
      --output-root live/demo/usdjpy_asia_range_london_oanda
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from .eod_charts import _parse_ny, _price_fmt

NY = pytz.timezone("America/New_York")
ASIA_START = dt_time(19, 0)
ASIA_END = dt_time(3, 0)
LONDON_EOD = dt_time(11, 59)


def _load_parity(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        sd = str(row.get("session_date") or "").strip()
        if not sd:
            continue
        # Prefer the London-open skip row over later eod sitout duplicates.
        prev = out.get(sd)
        if prev is None or str(row.get("decision") or "") == "skip":
            out[sd] = dict(row)
    return out


def _load_or_from_instance(state_root: Path) -> Dict[str, Dict[str, Any]]:
    path = state_root / "strategy_instances.csv"
    if not path.exists():
        return {}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return {}
    try:
        cfg = json.loads(rows[-1].get("config_json") or "{}")
    except json.JSONDecodeError:
        return {}
    raw = cfg.get("session_or_ranges") or {}
    return {str(k): dict(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _session_window(session: date) -> Tuple[datetime, datetime, datetime]:
    """Return (asia_start, asia_end/london_open, chart_end) in NY tz."""
    # Asia starts prior calendar evening.
    asia_start = NY.localize(datetime.combine(session - timedelta(days=1), ASIA_START))
    asia_end = NY.localize(datetime.combine(session, ASIA_END))
    chart_end = NY.localize(datetime.combine(session, LONDON_EOD)) + timedelta(minutes=6)
    return asia_start, asia_end, chart_end


def _load_1m_window(bars_path: Path, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if not bars_path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with bars_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = row.get("ts") or ""
            try:
                dt = _parse_ny(ts)
            except Exception:
                continue
            if dt < start or dt >= end:
                continue
            out.append(
                {
                    "dt": dt,
                    "o": float(row["open"]),
                    "h": float(row["high"]),
                    "l": float(row["low"]),
                    "c": float(row["close"]),
                }
            )
    return out


def _aggregate(bars: List[Dict[str, Any]], minutes: int = 5) -> List[Dict[str, Any]]:
    if not bars:
        return []
    buckets: Dict[datetime, List[Dict[str, Any]]] = {}
    for b in bars:
        dt = b["dt"]
        floored = dt.replace(minute=(dt.minute // minutes) * minutes, second=0, microsecond=0)
        buckets.setdefault(floored, []).append(b)
    out: List[Dict[str, Any]] = []
    for ts in sorted(buckets):
        chunk = buckets[ts]
        out.append(
            {
                "dt": ts,
                "o": chunk[0]["o"],
                "h": max(x["h"] for x in chunk),
                "l": min(x["l"] for x in chunk),
                "c": chunk[-1]["c"],
            }
        )
    return out


def _or_from_bars(bars_1m: List[Dict[str, Any]], asia_start: datetime, asia_end: datetime) -> Tuple[Optional[float], Optional[float]]:
    asia = [b for b in bars_1m if asia_start <= b["dt"] < asia_end]
    if not asia:
        return None, None
    return max(b["h"] for b in asia), min(b["l"] for b in asia)


def _load_session_fills(fills_path: Path, session: date) -> List[Dict[str, Any]]:
    """Fills whose NY calendar date matches ``session`` (London trade day)."""
    if not fills_path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with fills_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = row.get("ts") or ""
            try:
                dt = _parse_ny(ts)
            except Exception:
                continue
            if dt.date() != session:
                continue
            try:
                px = float(row.get("price") or 0.0)
                qty = float(row.get("quantity") or 0.0)
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "dt": dt,
                    "side": str(row.get("side") or "").lower(),
                    "price": px,
                    "qty": qty,
                    "reason": str(row.get("reason") or ""),
                }
            )
    return out


def write_session_chart(
    *,
    output_root: Path,
    session: date,
    bars_1m: List[Dict[str, Any]],
    asia_start: datetime,
    asia_end: datetime,
    chart_end: datetime,
    or_high: Optional[float],
    or_low: Optional[float],
    parity: Optional[Dict[str, str]] = None,
    fills: Optional[List[Dict[str, Any]]] = None,
    instrument: str = "USDJPY",
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    if len(bars_1m) < 10:
        return None

    bars = _aggregate(bars_1m, minutes=5)
    pf = _price_fmt(instrument)
    out_dir = output_root / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("usdjpy_asia_range_session_%s.png" % session.isoformat())

    decision = str((parity or {}).get("decision") or "?")
    reason = str((parity or {}).get("reason") or "")
    wr = (parity or {}).get("shadow_50_wr") or ""
    spf = (parity or {}).get("shadow_50_pf") or ""
    gate = "decision=%s" % decision
    if reason:
        gate += " reason=%s" % reason
    if wr or spf:
        gate += "  shadow50 wr=%s pf=%s" % (wr or "—", spf or "—")

    fig, ax = plt.subplots(figsize=(14, 5.5), dpi=120)
    # Window shading.
    ymin = min(b["l"] for b in bars)
    ymax = max(b["h"] for b in bars)
    pad = (ymax - ymin) * 0.08 or 0.05
    ax.axvspan(asia_start, asia_end, color="#cfe8ff", alpha=0.55, label="Asia OR 19:00–03:00")
    ax.axvspan(asia_end, chart_end, color="#ffe8cc", alpha=0.45, label="London window → 11:59")

    width = timedelta(minutes=3.5)
    for b in bars:
        color = "#1b7f4e" if b["c"] >= b["o"] else "#b33a3a"
        ax.plot([b["dt"], b["dt"]], [b["l"], b["h"]], color=color, linewidth=0.8, solid_capstyle="round")
        body_low = min(b["o"], b["c"])
        body_h = abs(b["c"] - b["o"]) or (ymax - ymin) * 0.001
        ax.add_patch(
            Rectangle(
                (mdates.date2num(b["dt"] - width / 2), body_low),
                mdates.date2num(b["dt"] + width / 2) - mdates.date2num(b["dt"] - width / 2),
                body_h,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
            )
        )

    if or_high is not None:
        ax.axhline(or_high, color="#1a4b8c", linestyle="--", linewidth=1.2, label=("OR high " + pf) % or_high)
    if or_low is not None:
        ax.axhline(or_low, color="#1a4b8c", linestyle=":", linewidth=1.2, label=("OR low " + pf) % or_low)

    entry_labeled = False
    exit_labeled = False
    for f in fills or []:
        dt = f["dt"]
        px = float(f["price"])
        reason = str(f.get("reason") or "").lower()
        side = str(f.get("side") or "").lower()
        is_entry = reason == "entry" or (not reason and side in {"buy", "sell"})
        if is_entry and reason in {"", "entry"}:
            marker = "v" if side == "sell" else "^"
            color = "#8b1a1a" if side == "sell" else "#0a5c2e"
            label = None
            if not entry_labeled:
                label = "entry %s %s @ %s" % (side, ("%.0f" % f["qty"]), pf % px)
                entry_labeled = True
            ax.scatter([dt], [px], marker=marker, s=120, color=color, zorder=6, label=label, edgecolors="white", linewidths=0.6)
            ax.annotate(
                "%s %s" % (side, pf % px),
                (dt, px),
                textcoords="offset points",
                xytext=(6, 10 if side == "buy" else -14),
                fontsize=8,
                color=color,
            )
        else:
            color = "#333333"
            label = None
            if not exit_labeled:
                label = "%s @ %s" % (reason or "exit", pf % px)
                exit_labeled = True
            ax.scatter([dt], [px], marker="X", s=90, color=color, zorder=6, label=label, linewidths=1.2)
            ax.annotate(
                "%s %s" % (reason or "exit", pf % px),
                (dt, px),
                textcoords="offset points",
                xytext=(6, -14),
                fontsize=8,
                color=color,
            )

    ax.axvline(asia_end, color="#666666", linestyle="-", linewidth=0.9, alpha=0.8)
    ax.set_xlim(asia_start, chart_end)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2, tz=NY))
    fig.autofmt_xdate()
    fill_note = ""
    if fills:
        fill_note = "  |  fills=%d" % len(fills)
    ax.set_title(
        "USDJPY Asia-range London  session=%s  (5m)%s\n%s" % (session.isoformat(), fill_note, gate),
        fontsize=11,
    )
    ax.set_ylabel("price")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def write_index(output_root: Path, written: List[Tuple[date, Path, Dict[str, str]]]) -> Path:
    charts = output_root / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    index = charts / "INDEX.html"
    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>USDJPY Asia-range session charts</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#111;color:#eee}",
        "h1{font-size:1.2rem} .card{margin:0 0 28px} img{max-width:100%;border:1px solid #333}",
        "p{color:#aaa;font-size:0.9rem}</style></head><body>",
        "<h1>USDJPY Asia-range trade window (Asia OR 19:00–03:00 → London EOD 11:59 NY)</h1>",
        "<p>Demo: %s — OR + gate annotation; entry/exit markers when fills.csv has the session.</p>" % output_root,
    ]
    for session, path, parity in written:
        gate = "%s/%s" % (parity.get("decision") or "?", parity.get("reason") or "")
        wr = parity.get("shadow_50_wr") or "—"
        pf = parity.get("shadow_50_pf") or "—"
        lines.append("<div class='card'>")
        lines.append("<h2>%s — %s (shadow50 wr=%s pf=%s)</h2>" % (session.isoformat(), gate, wr, pf))
        lines.append("<img src='%s' alt='%s'/>" % (path.name, session.isoformat()))
        lines.append("</div>")
    lines.append("</body></html>")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index


def run(output_root: Path, *, only_sessions: Optional[List[str]] = None) -> List[Path]:
    state = output_root / "state"
    bars_path = state / "bars" / "USDJPY_1m.csv"
    parity = _load_parity(output_root / "campaign_parity.csv")
    ors = _load_or_from_instance(state)
    fills_path = state / "fills.csv"

    # Prefer sessions with an OR or a parity row; always include live-fill days.
    sessions = set(parity) | set(ors)
    if fills_path.exists():
        with fills_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    sessions.add(_parse_ny(row.get("ts") or "").date().isoformat())
                except Exception:
                    continue
    if only_sessions:
        sessions = set(only_sessions) & sessions if sessions else set(only_sessions)
        if only_sessions and not sessions:
            sessions = set(only_sessions)
    written_meta: List[Tuple[date, Path, Dict[str, str]]] = []
    paths: List[Path] = []
    for sd in sorted(sessions):
        try:
            session = date.fromisoformat(sd)
        except ValueError:
            continue
        asia_start, asia_end, chart_end = _session_window(session)
        bars = _load_1m_window(bars_path, asia_start, chart_end)
        or_meta = ors.get(sd) or {}
        or_high = or_meta.get("high")
        or_low = or_meta.get("low")
        try:
            or_high = float(or_high) if or_high is not None else None
            or_low = float(or_low) if or_low is not None else None
        except (TypeError, ValueError):
            or_high, or_low = None, None
        if or_high is None or or_low is None:
            or_high, or_low = _or_from_bars(bars, asia_start, asia_end)
        sess_fills = _load_session_fills(fills_path, session)
        # Prefer a take/skip decision row over eod defer spam when annotating.
        p_row = parity.get(sd) or {}
        if str(p_row.get("decision") or "") == "eod" and sess_fills:
            p_row = dict(p_row)
            p_row["decision"] = "take"
            p_row["reason"] = "live_fills"
        path = write_session_chart(
            output_root=output_root,
            session=session,
            bars_1m=bars,
            asia_start=asia_start,
            asia_end=asia_end,
            chart_end=chart_end,
            or_high=or_high,
            or_low=or_low,
            parity=p_row,
            fills=sess_fills,
        )
        if path is not None:
            paths.append(path)
            written_meta.append((session, path, p_row))
    if written_meta:
        # Keep full index: merge newly written with existing chart PNGs when filtering.
        if only_sessions:
            existing: List[Tuple[date, Path, Dict[str, str]]] = []
            charts = output_root / "charts"
            for p in sorted(charts.glob("usdjpy_asia_range_session_*.png")):
                try:
                    sd = p.stem.split("_")[-1]
                    d = date.fromisoformat(sd)
                except ValueError:
                    continue
                if any(s == d for s, _, _ in written_meta):
                    continue
                existing.append((d, p, parity.get(sd) or {}))
            written_meta = sorted(existing + written_meta, key=lambda x: x[0])
        write_index(output_root, written_meta)
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--output-root",
        default="live/demo/usdjpy_asia_range_london_oanda",
        help="Asia-range demo root (contains state/ + campaign_parity.csv)",
    )
    ap.add_argument(
        "--session",
        action="append",
        default=[],
        help="Only render these YYYY-MM-DD sessions (repeatable)",
    )
    args = ap.parse_args(argv)
    root = Path(args.output_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    paths = run(root, only_sessions=list(args.session) or None)
    print("wrote %d charts under %s/charts" % (len(paths), root))
    for p in paths:
        print(" ", p)
    idx = root / "charts" / "INDEX.html"
    if idx.exists():
        print("index:", idx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
