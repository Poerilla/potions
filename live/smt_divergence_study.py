from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NQ_4H = ROOT / "nq" / "data" / "nq_front_month_4h_from_1m.csv"
DEFAULT_ES_4H = ROOT / "es" / "data" / "es_front_month_4h_from_1m.csv"
DEFAULT_OUT = ROOT / "live" / "state" / "smt_divergence_4h_nq_es"
DEFAULT_NQ_DAILY = ROOT / "nq" / "nq_daily.csv"
DEFAULT_ES_DAILY = ROOT / "es" / "es_daily.csv"
DEFAULT_OUT_DAILY = ROOT / "live" / "state" / "smt_divergence_daily_nq_es"


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Pivot:
    ts: datetime
    price: float
    kind: str  # "high" or "low"


@dataclass(frozen=True)
class Divergence:
    ts: datetime
    kind: str  # "bearish_high" | "bullish_low"
    leader: str
    lagger: str
    leader_curr: float
    leader_prev: float
    lagger_curr: float
    lagger_prev: float


def _parse_ts(value: str) -> datetime:
    text = str(value).strip().replace(" ", "T", 1)
    return datetime.fromisoformat(text)


def _read_bars(path: Path, ts_field: str) -> List[Bar]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: List[Bar] = []
    for row in rows:
        out.append(
            Bar(
                ts=_parse_ts(row[ts_field]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        )
    out.sort(key=lambda b: b.ts)
    return out


def _align(nq: List[Bar], es: List[Bar]) -> Tuple[List[Bar], List[Bar]]:
    nq_by = {b.ts: b for b in nq}
    es_by = {b.ts: b for b in es}
    common = sorted(set(nq_by).intersection(es_by))
    return [nq_by[ts] for ts in common], [es_by[ts] for ts in common]


def _pivot_highs(bars: List[Bar], left: int, right: int) -> List[Pivot]:
    out: List[Pivot] = []
    highs = [b.high for b in bars]
    for i in range(left, len(bars) - right):
        center = highs[i]
        if center <= max(highs[i - left : i]):
            continue
        if center < max(highs[i + 1 : i + 1 + right]):
            continue
        out.append(Pivot(ts=bars[i].ts, price=center, kind="high"))
    return out


def _pivot_lows(bars: List[Bar], left: int, right: int) -> List[Pivot]:
    out: List[Pivot] = []
    lows = [b.low for b in bars]
    for i in range(left, len(bars) - right):
        center = lows[i]
        if center >= min(lows[i - left : i]):
            continue
        if center > min(lows[i + 1 : i + 1 + right]):
            continue
        out.append(Pivot(ts=bars[i].ts, price=center, kind="low"))
    return out


def _last_pivot_at_or_before(pivots: List[Pivot], ts: datetime) -> Optional[int]:
    idx: Optional[int] = None
    for i, pv in enumerate(pivots):
        if pv.ts <= ts:
            idx = i
        else:
            break
    return idx


def _scan_side(
    leader_name: str,
    lagger_name: str,
    leader: List[Pivot],
    lagger: List[Pivot],
    side: str,
) -> List[Divergence]:
    out: List[Divergence] = []
    for i in range(1, len(leader)):
        prev = leader[i - 1]
        curr = leader[i]
        if side == "high":
            if curr.price <= prev.price:
                continue
        else:
            if curr.price >= prev.price:
                continue

        j = _last_pivot_at_or_before(lagger, curr.ts)
        if j is None or j < 1:
            continue
        lag_prev = lagger[j - 1]
        lag_curr = lagger[j]

        if side == "high":
            lag_confirms = lag_curr.price > lag_prev.price
            if lag_confirms:
                continue
            out.append(
                Divergence(
                    ts=curr.ts,
                    kind="bearish_high",
                    leader=leader_name,
                    lagger=lagger_name,
                    leader_curr=curr.price,
                    leader_prev=prev.price,
                    lagger_curr=lag_curr.price,
                    lagger_prev=lag_prev.price,
                )
            )
        else:
            lag_confirms = lag_curr.price < lag_prev.price
            if lag_confirms:
                continue
            out.append(
                Divergence(
                    ts=curr.ts,
                    kind="bullish_low",
                    leader=leader_name,
                    lagger=lagger_name,
                    leader_curr=curr.price,
                    leader_prev=prev.price,
                    lagger_curr=lag_curr.price,
                    lagger_prev=lag_prev.price,
                )
            )
    return out


def _collect_divergences(nq: List[Bar], es: List[Bar], left: int, right: int) -> List[Divergence]:
    nq_hi = _pivot_highs(nq, left, right)
    nq_lo = _pivot_lows(nq, left, right)
    es_hi = _pivot_highs(es, left, right)
    es_lo = _pivot_lows(es, left, right)

    out: List[Divergence] = []
    out.extend(_scan_side("NQ", "ES", nq_hi, es_hi, "high"))
    out.extend(_scan_side("ES", "NQ", es_hi, nq_hi, "high"))
    out.extend(_scan_side("NQ", "ES", nq_lo, es_lo, "low"))
    out.extend(_scan_side("ES", "NQ", es_lo, nq_lo, "low"))

    # De-dup exact repeats (same ts/kind/leader/lagger)
    uniq: Dict[Tuple[datetime, str, str, str], Divergence] = {}
    for d in out:
        uniq[(d.ts, d.kind, d.leader, d.lagger)] = d
    return sorted(uniq.values(), key=lambda d: d.ts)


def _add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def _window_bounds(start: datetime, end: datetime, months: int = 6) -> List[Tuple[datetime, datetime]]:
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out: List[Tuple[datetime, datetime]] = []
    while cur <= end:
        nxt = _add_months(cur, months)
        out.append((cur, nxt))
        cur = nxt
    return out


def _norm_close(bars: List[Bar]) -> List[float]:
    if not bars:
        return []
    base = bars[0].close if bars[0].close else 1.0
    return [100.0 * (b.close / base) for b in bars]


def _plot_window(
    out: Path,
    nq: List[Bar],
    es: List[Bar],
    events: List[Divergence],
    window_start: datetime,
    window_end: datetime,
    timeframe_label: str,
) -> None:
    nq_win = [b for b in nq if window_start <= b.ts < window_end]
    es_win = [b for b in es if window_start <= b.ts < window_end]
    if not nq_win or not es_win:
        return
    ev_win = [e for e in events if window_start <= e.ts < window_end]

    nq_norm = _norm_close(nq_win)
    es_norm = _norm_close(es_win)
    nq_by_ts = {b.ts: v for b, v in zip(nq_win, nq_norm)}
    es_by_ts = {b.ts: v for b, v in zip(es_win, es_norm)}

    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot([b.ts for b in nq_win], nq_norm, color="#2563eb", linewidth=1.35, label="NQ close (normalized)")
    ax.plot([b.ts for b in es_win], es_norm, color="#7c3aed", linewidth=1.35, label="ES close (normalized)")

    red_x: List[datetime] = []
    red_y: List[float] = []
    green_x: List[datetime] = []
    green_y: List[float] = []
    for e in ev_win:
        y_val = nq_by_ts.get(e.ts) if e.leader == "NQ" else es_by_ts.get(e.ts)
        if y_val is None:
            continue
        if e.kind == "bearish_high":
            red_x.append(e.ts)
            red_y.append(y_val)
        else:
            green_x.append(e.ts)
            green_y.append(y_val)

    if red_x:
        ax.scatter(red_x, red_y, color="#dc2626", s=26, zorder=5, label="Bearish SMT (divergent high)")
    if green_x:
        ax.scatter(green_x, green_y, color="#16a34a", s=26, zorder=5, label="Bullish SMT (divergent low)")

    end_label = (window_end - timedelta(seconds=1)).date()
    ax.set_title(
        f"NQ vs ES {timeframe_label} SMT Divergence"
        f"\nWindow {window_start.date()} to {end_label} "
        f"| bearish: {len(red_x)} | bullish: {len(green_x)}"
    )
    ax.set_ylabel("Normalized close (start=100)")
    ax.grid(True, alpha=0.18)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=45)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _write_events_csv(path: Path, events: Iterable[Divergence]) -> None:
    rows = [
        {
            "ts": e.ts.isoformat(),
            "kind": e.kind,
            "leader": e.leader,
            "lagger": e.lagger,
            "leader_prev": f"{e.leader_prev:.4f}",
            "leader_curr": f"{e.leader_curr:.4f}",
            "lagger_prev": f"{e.lagger_prev:.4f}",
            "lagger_curr": f"{e.lagger_curr:.4f}",
        }
        for e in events
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_index_md(
    out_root: Path,
    charts: List[Path],
    events: List[Divergence],
    windows: List[Tuple[datetime, datetime]],
    timeframe_label: str,
) -> None:
    bearish = [e for e in events if e.kind == "bearish_high"]
    bullish = [e for e in events if e.kind == "bullish_low"]
    lines = [
        f"# NQ vs ES {timeframe_label} SMT Divergence Study",
        "",
        f"Pivot-based SMT scan on {timeframe_label} bars:",
        "",
        "- Bearish SMT: one index makes a higher high while the other fails to make a higher high.",
        "- Bullish SMT: one index makes a lower low while the other fails to make a lower low.",
        "",
        f"- Total divergences: **{len(events)}**",
        f"- Bearish highs (red dots): **{len(bearish)}**",
        f"- Bullish lows (green dots): **{len(bullish)}**",
        f"- Windows (6 months each): **{len(windows)}**",
        "",
        "## Charts",
        "",
    ]
    by_year: Dict[int, List[Path]] = {}
    for p in charts:
        year = int(p.parent.name)
        by_year.setdefault(year, []).append(p)
    for year in sorted(by_year):
        lines.append(f"### {year}")
        lines.append("")
        for p in sorted(by_year[year]):
            rel = p.relative_to(out_root)
            lines.append(f"- [{p.stem}]({rel.as_posix()})")
        lines.append("")
    lines.extend(
        [
            "## Files",
            "",
            "- [events.csv](events.csv)",
            "- [summary.csv](summary.csv)",
            "",
        ]
    )
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_summary_csv(path: Path, events: List[Divergence]) -> None:
    leader_counts: Dict[str, Dict[str, int]] = {
        "NQ": {"bearish_high": 0, "bullish_low": 0},
        "ES": {"bearish_high": 0, "bullish_low": 0},
    }
    for e in events:
        leader_counts[e.leader][e.kind] += 1
    rows = [
        {
            "leader": leader,
            "bearish_high_count": str(counts["bearish_high"]),
            "bullish_low_count": str(counts["bullish_low"]),
            "total": str(counts["bearish_high"] + counts["bullish_low"]),
        }
        for leader, counts in leader_counts.items()
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def run(
    nq_path: Path = DEFAULT_NQ_4H,
    es_path: Path = DEFAULT_ES_4H,
    output_root: Path = DEFAULT_OUT,
    nq_ts_field: str = "time",
    es_ts_field: str = "time",
    timeframe_label: str = "4H",
    pivot_left: int = 2,
    pivot_right: int = 2,
) -> Dict[str, int]:
    nq = _read_bars(nq_path, nq_ts_field)
    es = _read_bars(es_path, es_ts_field)
    nq, es = _align(nq, es)
    if not nq or not es:
        raise ValueError(f"No overlapping NQ/ES {timeframe_label} bars found.")

    events = _collect_divergences(nq, es, pivot_left, pivot_right)
    windows = _window_bounds(nq[0].ts, nq[-1].ts, months=6)
    charts: List[Path] = []
    for start, end in windows:
        out = output_root / "charts" / f"{start.year:04d}" / f"{start.year:04d}_{start.month:02d}_to_{end.year:04d}_{end.month:02d}.png"
        _plot_window(out, nq, es, events, start, end, timeframe_label=timeframe_label)
        if out.exists():
            charts.append(out)

    output_root.mkdir(parents=True, exist_ok=True)
    _write_events_csv(output_root / "events.csv", events)
    _write_summary_csv(output_root / "summary.csv", events)
    _write_index_md(output_root, charts, events, windows, timeframe_label=timeframe_label)

    return {
        "bars": len(nq),
        "events_total": len(events),
        "events_bearish": len([e for e in events if e.kind == "bearish_high"]),
        "events_bullish": len([e for e in events if e.kind == "bullish_low"]),
        "charts": len(charts),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NQ/ES SMT divergence study and chart pack.")
    p.add_argument("--timeframe", choices=["4h", "daily"], default="4h")
    p.add_argument("--nq-path", type=Path, default=None)
    p.add_argument("--es-path", type=Path, default=None)
    p.add_argument("--output-root", type=Path, default=None)
    p.add_argument("--nq-ts-field", type=str, default=None)
    p.add_argument("--es-ts-field", type=str, default=None)
    p.add_argument("--pivot-left", type=int, default=2)
    p.add_argument("--pivot-right", type=int, default=2)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeframe == "daily":
        nq_path = args.nq_path or DEFAULT_NQ_DAILY
        es_path = args.es_path or DEFAULT_ES_DAILY
        output_root = args.output_root or DEFAULT_OUT_DAILY
        nq_ts_field = args.nq_ts_field or "date"
        es_ts_field = args.es_ts_field or "date"
        timeframe_label = "Daily"
    else:
        nq_path = args.nq_path or DEFAULT_NQ_4H
        es_path = args.es_path or DEFAULT_ES_4H
        output_root = args.output_root or DEFAULT_OUT
        nq_ts_field = args.nq_ts_field or "time"
        es_ts_field = args.es_ts_field or "time"
        timeframe_label = "4H"

    stats = run(
        nq_path=nq_path,
        es_path=es_path,
        output_root=output_root,
        nq_ts_field=nq_ts_field,
        es_ts_field=es_ts_field,
        timeframe_label=timeframe_label,
        pivot_left=args.pivot_left,
        pivot_right=args.pivot_right,
    )
    print(
        "SMT study complete: bars={bars}, events={events_total} (bearish={events_bearish}, bullish={events_bullish}), charts={charts}".format(
            **stats
        )
    )
    print(f"Wrote {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

