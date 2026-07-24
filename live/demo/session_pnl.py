"""Session FIFO PnL helpers for Pilot A ungated demos (paper + OANDA)."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pytz

from ..replay_audit import POINT_VALUES

NY = pytz.timezone("America/New_York")
RESULTS_FIELDS = ["demo", "session_date", "path", "usd"]


def _parse_ny(ts: str) -> datetime:
    raw = str(ts).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # OANDA can emit nanosecond fractions; Python 3.8 fromisoformat accepts ≤6 digits.
    if "." in raw:
        head, rest = raw.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        raw = "%s.%s%s" % (head, (frac + "000000")[:6], tz)
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(NY)


def load_session_fills(fills_path: Path, session: date) -> List[Dict[str, str]]:
    if not fills_path.exists():
        return []
    rows: List[Dict[str, str]] = []
    with fills_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                if _parse_ny(row["ts"]).date() == session:
                    rows.append(row)
            except Exception:
                continue
    return rows


def fifo_pnl_from_fills(fills: Sequence[Dict[str, str]], instrument: str) -> Tuple[float, float]:
    """Return ``(raw_price_pnl, usd)`` using FIFO inventory matching live paper audit."""

    qty = 0.0
    avg = 0.0
    realized = 0.0
    for f in fills:
        side = str(f.get("side") or "").lower()
        q = float(f.get("quantity") or 0)
        px = float(f.get("price") or 0)
        signed = q if side == "buy" else -q
        if qty == 0 or (qty > 0 and signed > 0) or (qty < 0 and signed < 0):
            new_qty = qty + signed
            if new_qty != 0:
                avg = ((avg * abs(qty)) + (px * abs(signed))) / abs(new_qty)
            else:
                avg = 0.0
            qty = new_qty
            continue
        close_q = min(abs(qty), abs(signed))
        if qty > 0:
            realized += (px - avg) * close_q
        else:
            realized += (avg - px) * close_q
        qty = qty + signed
        if qty == 0:
            avg = 0.0
        elif (qty > 0 and signed > 0) or (qty < 0 and signed < 0):
            avg = px
    pv = float(POINT_VALUES.get(instrument.upper(), 1.0))
    return realized, realized * pv


def summarize_fill_path(fills: Sequence[Dict[str, str]]) -> str:
    if not fills:
        return "no_fills"
    parts: List[str] = []
    for f in fills:
        reason = str(f.get("reason") or "").strip() or "fill"
        side = str(f.get("side") or "").lower()
        if reason == "entry":
            parts.append("long" if side == "buy" else "short")
            parts.append("entry")
        elif reason == "tp1":
            parts.append("TP1")
        elif reason in {"runner_stop", "wide_stop"}:
            parts.append("runner SL" if reason == "runner_stop" else "wide SL")
        elif reason == "eod_close":
            parts.append("EOD")
        elif reason == "tp2":
            parts.append("TP2")
        else:
            parts.append(reason)
    # Collapse "short entry" style
    out: List[str] = []
    i = 0
    while i < len(parts):
        if parts[i] in {"long", "short"} and i + 1 < len(parts) and parts[i + 1] == "entry":
            out.append("%s →" % parts[i])
            i += 2
            continue
        out.append(parts[i])
        i += 1
    text = " ".join(out).replace("→ ", "→ ")
    # Normalize to plan style: "short → TP1 → runner SL"
    text = text.replace("→ →", "→")
    if "→" not in text and len(parts) >= 2:
        # rebuild: direction then arrows
        direction = parts[0] if parts[0] in {"long", "short"} else ""
        rest = [p for p in parts[1:] if p != "entry"]
        if direction:
            return "%s → %s" % (direction, " → ".join(rest)) if rest else direction
    if text.startswith("short →") or text.startswith("long →"):
        # "short → entry TP1" → "short → TP1"
        text = text.replace("→ entry ", "→ ").replace("→ entry", "→")
    return text.strip(" →") or "fills"


def append_session_result(
    csv_path: Path,
    *,
    demo: str,
    session_date: date,
    instrument: str,
    fills_path: Path,
) -> Optional[Dict[str, str]]:
    """Append one session row (and refresh TOTAL) for ``demo`` on ``session_date``."""

    fills = load_session_fills(fills_path, session_date)
    _raw, usd = fifo_pnl_from_fills(fills, instrument)
    path = summarize_fill_path(fills)
    row = {
        "demo": demo,
        "session_date": session_date.isoformat(),
        "path": path,
        "usd": "%.2f" % usd,
    }
    existing = _read_rows(csv_path)
    # Replace same demo+date if present; drop TOTAL then recompute.
    kept = [
        r
        for r in existing
        if not (
            str(r.get("demo") or "").upper() == demo.upper()
            and str(r.get("session_date") or "") == session_date.isoformat()
        )
        and str(r.get("demo") or "").upper() != "TOTAL"
    ]
    kept.append(row)
    total = sum(float(r.get("usd") or 0) for r in kept if str(r.get("session_date") or "") == session_date.isoformat())
    kept.append(
        {
            "demo": "TOTAL",
            "session_date": session_date.isoformat(),
            "path": "",
            "usd": "%.2f" % total,
        }
    )
    _write_rows(csv_path, kept)
    return row


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_rows(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULTS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in RESULTS_FIELDS})
