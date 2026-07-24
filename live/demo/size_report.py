"""Demo artifact size reporting — weekend / weekly rotation planning."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pytz

NY = pytz.timezone("America/New_York")

# Paths relative to a demo output root (or glob patterns under it).
SIZE_TARGETS: Tuple[Tuple[str, str], ...] = (
    ("PROGRESS.log", "log"),
    ("run.log", "log"),
    ("RUN_META.json", "meta"),
    ("state/bars", "price_data"),
    ("state/events/rth_ticks", "price_data"),
    ("state/events/fx_ticks", "price_data"),
    ("state/events/raw_market_data", "price_data_mirror"),  # often duplicates rth_ticks; detail only
    ("state/events/stream_errors.jsonl", "log"),
    ("state/events/oanda_order_events.jsonl", "audit"),
    ("state/events/reconciliation_events.jsonl", "audit"),
    ("state/fills.csv", "audit"),
    ("state/orders.csv", "audit"),
    ("state/positions.csv", "audit"),
    ("state", "state_total"),
    ("charts", "charts"),
)


def _bytes_of(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total += int(child.stat().st_size)
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _fmt_bytes(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024.0 or unit == "GB":
            if unit == "B":
                return "%d%s" % (int(x), unit)
            return "%.2f%s" % (x, unit)
        x /= 1024.0
    return "%dB" % n


def collect_demo_sizes(output_root: Path) -> List[Dict[str, object]]:
    """Return size rows for known demo artifacts under ``output_root``."""
    root = Path(output_root)
    rows: List[Dict[str, object]] = []
    for rel, kind in SIZE_TARGETS:
        path = root / rel
        nbytes = _bytes_of(path)
        if nbytes <= 0 and not path.exists():
            continue
        rows.append(
            {
                "path": rel,
                "kind": kind,
                "bytes": nbytes,
                "human": _fmt_bytes(nbytes),
                "exists": path.exists(),
            }
        )
    # Explicit per-bar CSVs (detail only — kind totals already include state/bars/).
    bars_dir = root / "state" / "bars"
    if bars_dir.is_dir():
        for csv_path in sorted(bars_dir.glob("*.csv")):
            nbytes = _bytes_of(csv_path)
            rows.append(
                {
                    "path": "state/bars/%s" % csv_path.name,
                    "kind": "price_data_detail",
                    "bytes": nbytes,
                    "human": _fmt_bytes(nbytes),
                    "exists": True,
                }
            )
    return rows


def summarize_by_kind(rows: Iterable[Dict[str, object]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        kind = str(row.get("kind") or "other")
        # Avoid double-counting aggregates / detail duplicates in kind rollups.
        if kind in {"state_total", "price_data_detail", "price_data_mirror"}:
            continue
        out[kind] = out.get(kind, 0) + int(row.get("bytes") or 0)
    return out


def format_size_report(
    output_root: Path,
    *,
    label: str,
    session_date: Optional[date] = None,
) -> List[str]:
    """Lines suitable for PROGRESS.log."""
    root = Path(output_root)
    rows = collect_demo_sizes(root)
    by_kind = summarize_by_kind(rows)
    when = session_date or datetime.now(tz=NY).date()
    lines = [
        "FILE_SIZES %s demo=%s date=%s ET"
        % (label, root.name, when.isoformat()),
    ]
    for kind in ("price_data", "log", "audit", "charts", "meta"):
        if kind in by_kind:
            lines.append("FILE_SIZES_KIND %s=%s (%d bytes)" % (kind, _fmt_bytes(by_kind[kind]), by_kind[kind]))
    state_total = next((int(r["bytes"]) for r in rows if r.get("path") == "state"), 0)
    lines.append("FILE_SIZES_KIND state_total=%s (%d bytes)" % (_fmt_bytes(state_total), state_total))
    # Detail lines — price + logs first.
    detail_paths = {
        "PROGRESS.log",
        "run.log",
        "state/bars",
        "state/events/rth_ticks",
        "state/events/fx_ticks",
        "state/events/raw_market_data",
    }
    for row in rows:
        path = str(row.get("path") or "")
        kind = str(row.get("kind") or "")
        if kind == "price_data_detail" or path in detail_paths:
            lines.append("FILE_SIZE %s %s %s" % (path, row["human"], row["bytes"]))
    for row in rows:
        path = str(row.get("path") or "")
        kind = str(row.get("kind") or "")
        if kind in {"price_data", "log", "price_data_detail", "price_data_mirror", "state_total"}:
            continue
        if path in detail_paths or path == "state":
            continue
        lines.append("FILE_SIZE %s %s %s" % (path, row["human"], row["bytes"]))
    # Rotation hint
    progress = next((int(r["bytes"]) for r in rows if r.get("path") == "PROGRESS.log"), 0)
    run_log = next((int(r["bytes"]) for r in rows if r.get("path") == "run.log"), 0)
    price = by_kind.get("price_data", 0)
    lines.append(
        "FILE_SIZES_ROTATION_HINT progress=%s run_log=%s price_data=%s "
        "(rotate logs ~50–100MB; archive/prune price ticks/bars if price_data >> 1GB)"
        % (_fmt_bytes(progress), _fmt_bytes(run_log), _fmt_bytes(price))
    )
    return lines


def append_size_report(
    output_root: Path,
    log: Callable[[Path, str], None],
    *,
    label: str,
    session_date: Optional[date] = None,
) -> Path:
    """Write size lines to PROGRESS via ``log`` and append a durable copy under the demo root."""
    lines = format_size_report(output_root, label=label, session_date=session_date)
    for line in lines:
        log(output_root, line)
    out = Path(output_root) / "FILE_SIZES.log"
    stamp = datetime.now(tz=NY).isoformat(timespec="seconds")
    with out.open("a", encoding="utf-8") as fh:
        fh.write("# %s\n" % stamp)
        for line in lines:
            fh.write(line + "\n")
        fh.write("\n")
    return out


def is_friday_ny(ts: str) -> bool:
    from ..oanda import parse_oanda_ts

    dt = parse_oanda_ts(ts)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY).weekday() == 4  # Mon=0 … Fri=4


def write_baseline_inventory(demo_root: Path, out_path: Path) -> Path:
    """One-shot inventory across all demo dirs (weekend baseline)."""
    demo_root = Path(demo_root)
    lines = [
        "# Demo file-size baseline",
        "",
        "Generated: %s ET" % datetime.now(tz=NY).isoformat(timespec="seconds"),
        "",
    ]
    grand = {"price_data": 0, "log": 0, "audit": 0, "charts": 0, "state_total": 0}
    for child in sorted(demo_root.iterdir()):
        if not child.is_dir():
            continue
        if not (child.name.endswith("_paper") or child.name.endswith("_oanda")):
            continue
        if not (child / "PROGRESS.log").exists() and not (child / "state").exists():
            continue
        rows = collect_demo_sizes(child)
        by_kind = summarize_by_kind(rows)
        state_total = next((int(r["bytes"]) for r in rows if r.get("path") == "state"), 0)
        lines.append("## %s" % child.name)
        lines.append("")
        lines.append("| path | kind | size | bytes |")
        lines.append("|------|------|------|------:|")
        for row in rows:
            lines.append("| `%s` | %s | %s | %s |" % (row["path"], row["kind"], row["human"], row["bytes"]))
        lines.append("")
        lines.append(
            "Kind totals: price_data=%s log=%s audit=%s charts=%s state_total=%s"
            % (
                _fmt_bytes(by_kind.get("price_data", 0)),
                _fmt_bytes(by_kind.get("log", 0)),
                _fmt_bytes(by_kind.get("audit", 0)),
                _fmt_bytes(by_kind.get("charts", 0)),
                _fmt_bytes(state_total),
            )
        )
        lines.append("")
        grand["price_data"] += by_kind.get("price_data", 0)
        grand["log"] += by_kind.get("log", 0)
        grand["audit"] += by_kind.get("audit", 0)
        grand["charts"] += by_kind.get("charts", 0)
        grand["state_total"] += state_total
    lines.append("## Grand totals (all demos)")
    lines.append("")
    for k, v in grand.items():
        lines.append("- **%s**: %s (%d bytes)" % (k, _fmt_bytes(v), v))
    lines.append("")
    lines.append(
        "Rotation planning: watch `PROGRESS.log` / `run.log` toward 50–100MB; "
        "`state/events/*_ticks` and `state/bars` dominate long-run growth."
    )
    out_path = Path(out_path)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
