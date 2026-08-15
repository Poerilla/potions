"""Shadow risk-guard for live OANDA practice books.

Monitors strategy-owned open exposure and **logs** actions it would take when
open adverse excursion reaches the book's average loss (scale-aware). Does
**not** freeze entries, close trades, or stop demos.

Window: armed through ``SHADOW_UNTIL`` (default 2026-08-28, ~2 weeks).

Threshold source (for now): ``avg_loss`` from
``live/demo/oanda_practice_snapshot/strategy_avg_loss_mae_proxy.csv``.
After winner-MAE / percentile-carry research, swap to MAE-based thresholds if favorable.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.risk_guard_shadow --once --email
  python -m live.risk_guard_shadow --loop --interval 120
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .replay_audit import POINT_VALUES

DEMO_ROOT = REPO / "live" / "demo"
HUB = REPO / "live" / "state" / "risk_guard_shadow"
MAE_HUB = REPO / "live" / "state" / "oanda_winner_mae_carry"
THRESHOLDS_CSV = DEMO_ROOT / "oanda_practice_snapshot" / "strategy_avg_loss_mae_proxy.csv"
SHADOW_UNTIL = date(2026, 8, 28)  # ~2 weeks from 2026-08-14
DEFAULT_INTERVAL_SEC = 120

ACTION_COLS = [
    "ts",
    "demo",
    "strategy_id",
    "instrument",
    "mode",
    "open_qty",
    "avg_price",
    "mark",
    "adverse_pts",
    "adverse_usd_est",
    "threshold_pts",
    "threshold_usd_est",
    "threshold_source",
    "breach",
    "would_action",
    "detail",
]


@dataclass
class BookThreshold:
    demo: str
    strategy_id: str
    instrument: str
    live_scale_hint: float
    avg_loss_unit_usd: float
    avg_loss_pts: float
    planned_risk_pts: Optional[float]
    threshold_source: str
    tape: str = ""


@dataclass
class OpenBook:
    demo: str
    strategy_id: str
    instrument: str
    open_qty: float
    avg_price: float
    mark: Optional[float]
    source: str  # local | oanda


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _progress(msg: str) -> None:
    line = "[%s] %s" % (_iso(), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_csv(path: Path, rows: Sequence[Dict[str, Any]], cols: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cols), extrasaction="ignore")
        if write_header:
            w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})


def _parse_float(raw: Any, default: float = 0.0) -> float:
    try:
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _avg_loss_pts_from_tape(tape_rel: str, instrument: str) -> Tuple[float, Optional[float]]:
    """Return (avg_loss_pts, planned_risk_pts_med) from research tape."""
    path = REPO / "live" / "state" / tape_rel
    if not path.exists():
        return float("nan"), None
    df = pd.read_csv(path)
    pnl_col = "usd" if "usd" in df.columns else ("net_usd" if "net_usd" in df.columns else None)
    if pnl_col is None:
        return float("nan"), None
    pnl = df[pnl_col].astype(float)
    losses = df[pnl < 0]
    planned = None
    if {"entry_price", "hard_stop_price", "direction"}.issubset(df.columns):
        ep = df["entry_price"].astype(float)
        hs = df["hard_stop_price"].astype(float)
        d = df["direction"].astype(str).str.lower()
        risk = pd.Series(
            [float(ep.iloc[i] - hs.iloc[i]) if str(d.iloc[i]).startswith("l") else float(hs.iloc[i] - ep.iloc[i]) for i in range(len(df))],
            index=df.index,
        ).clip(lower=0)
        planned = float(risk.median()) if len(risk) else None
    if "points" in losses.columns and len(losses):
        pts = losses["points"].astype(float).abs()
        return float(pts.mean()), planned
    if {"entry_price", "exit_price", "direction"}.issubset(losses.columns) and len(losses):
        ep = losses["entry_price"].astype(float)
        xp = losses["exit_price"].astype(float)
        d = losses["direction"].astype(str).str.lower()
        pts = [
            float(ep.iloc[i] - xp.iloc[i]) if str(d.iloc[i]).startswith("l") else float(xp.iloc[i] - ep.iloc[i])
            for i in range(len(losses))
        ]
        return float(pd.Series(pts).clip(lower=0).mean()), planned
    # Fall back: convert $ loss via research point value (JPY rough).
    pv = float(POINT_VALUES.get(instrument, 1.0) or 1.0)
    if pv <= 0 or not len(losses):
        return float("nan"), planned
    usd = (-losses[pnl_col].astype(float)).mean()
    # JPY-quoted research tapes are already USD-normalized in many hubs; keep $ as pts proxy flagged upstream.
    return float(usd / pv), planned


def load_thresholds() -> Dict[str, BookThreshold]:
    if not THRESHOLDS_CSV.exists():
        raise FileNotFoundError(THRESHOLDS_CSV)
    raw = pd.read_csv(THRESHOLDS_CSV)
    out: Dict[str, BookThreshold] = {}
    for _, row in raw.iterrows():
        demo = str(row["demo"])
        demo_dir = DEMO_ROOT / demo
        meta: Dict[str, Any] = {}
        if (demo_dir / "RUN_META.json").exists():
            meta = json.loads((demo_dir / "RUN_META.json").read_text(encoding="utf-8"))
        strategy_id = str(meta.get("strategy_id") or demo)
        instrument = str(meta.get("instrument") or row.get("instrument") or "")
        tape = str(row.get("tape") or "")
        avg_loss_pts, planned = _avg_loss_pts_from_tape(tape, instrument)
        # Prefer planned risk pts when avg_loss_pts collapsed (FX $ / huge PV).
        if (not (avg_loss_pts == avg_loss_pts) or avg_loss_pts <= 0) and planned and planned > 0:
            avg_loss_pts = float(planned)
            src = "planned_risk_pts"
        elif avg_loss_pts == avg_loss_pts and avg_loss_pts > 0:
            src = "avg_loss_pts"
        else:
            # Last resort: RUN_META stop_pts
            stop_pts = meta.get("stop_pts")
            avg_loss_pts = float(stop_pts) if stop_pts is not None else float("nan")
            src = "run_meta_stop_pts" if stop_pts is not None else "missing"
        out[demo] = BookThreshold(
            demo=demo,
            strategy_id=strategy_id,
            instrument=instrument,
            live_scale_hint=_parse_float(row.get("live_scale_hint"), 1.0) or 1.0,
            avg_loss_unit_usd=_parse_float(row.get("avg_loss_unit_usd")),
            avg_loss_pts=float(avg_loss_pts) if avg_loss_pts == avg_loss_pts else float("nan"),
            planned_risk_pts=planned,
            threshold_source=src,
            tape=tape,
        )
    # Overlay pXX winner-MAE thresholds for books marked favorable by MAE study.
    mae_csv = MAE_HUB / "summary.csv"
    if mae_csv.exists():
        try:
            import re

            mae = pd.read_csv(mae_csv)
            for _, mrow in mae.iterrows():
                demo = str(mrow.get("demo") or "")
                if demo not in out:
                    continue
                fav = bool(mrow.get("favorable_for_daemon"))
                thr = str(mrow.get("recommended_threshold") or "")
                m = re.fullmatch(r"p(\d+)_winner_mae", thr)
                if not (fav and m):
                    continue
                pct = m.group(1)
                pts = _parse_float(mrow.get("winner_mae_p%s_pts" % pct), float("nan"))
                if pts == pts and pts > 0:
                    book = out[demo]
                    book.avg_loss_pts = float(pts)
                    book.threshold_source = thr
                    out[demo] = book
        except Exception as exc:
            _progress("mae_overlay_skip %s" % exc)
    return out


def _last_mark(demo_dir: Path, instrument: str) -> Optional[float]:
    bars = demo_dir / "state" / "bars" / ("%s_1m.csv" % instrument)
    if not bars.exists() or bars.stat().st_size == 0:
        return None
    try:
        # Read only the tail cheaply.
        with bars.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            chunk = fh.read().decode("utf-8", "replace")
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        header = None
        # Prefer full header from file start if tail lacks it.
        with bars.open("r", encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
        last = lines[-1].split(",")
        row = dict(zip(header, last))
        for key in ("bid_close", "close", "ask_close"):
            if key in row and row[key] not in ("", None):
                return float(row[key])
    except Exception:
        return None
    return None


def _local_open_books() -> List[OpenBook]:
    books: List[OpenBook] = []
    for demo_dir in sorted(DEMO_ROOT.glob("*_oanda")):
        pos_path = demo_dir / "state" / "positions.csv"
        if not pos_path.exists() or pos_path.stat().st_size == 0:
            continue
        meta = {}
        if (demo_dir / "RUN_META.json").exists():
            meta = json.loads((demo_dir / "RUN_META.json").read_text(encoding="utf-8"))
        strategy_id = str(meta.get("strategy_id") or demo_dir.name)
        with pos_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                qty = _parse_float(row.get("quantity"))
                if abs(qty) < 1e-12:
                    continue
                inst = str(row.get("instrument") or meta.get("instrument") or "")
                avg = _parse_float(row.get("avg_price"))
                mark = _last_mark(demo_dir, inst)
                books.append(
                    OpenBook(
                        demo=demo_dir.name,
                        strategy_id=str(row.get("strategy_id") or strategy_id),
                        instrument=inst,
                        open_qty=qty,
                        avg_price=avg,
                        mark=mark,
                        source="local",
                    )
                )
    return books


def _oanda_open_books() -> List[OpenBook]:
    """Optional enrichment from practice account (tagged ownership)."""
    try:
        from .demo.oanda_practice_sync import fetch_account, owned_open_by_strategy, summarize
        from .oanda import OandaConfig
    except Exception as exc:
        _progress("oanda_import_skip %s" % exc)
        return []
    env_path = DEMO_ROOT / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v
    try:
        cfg = OandaConfig.from_env()
        body, broker, _ = fetch_account(cfg)
        summary = summarize(body, broker)
        owned = owned_open_by_strategy(broker.client, summary)
    except Exception as exc:
        _progress("oanda_fetch_skip %s" % exc)
        return []
    # Map strategy_id -> demo folder
    sid_to_demo: Dict[str, str] = {}
    for demo_dir in DEMO_ROOT.glob("*_oanda"):
        if not (demo_dir / "RUN_META.json").exists():
            continue
        meta = json.loads((demo_dir / "RUN_META.json").read_text(encoding="utf-8"))
        sid_to_demo[str(meta.get("strategy_id") or demo_dir.name)] = demo_dir.name
    out: List[OpenBook] = []
    for sid, by_inst in owned.items():
        demo = sid_to_demo.get(sid, sid)
        demo_dir = DEMO_ROOT / demo if (DEMO_ROOT / demo).exists() else None
        for inst, payload in by_inst.items():
            qty = float(payload.get("qty") or 0)
            if abs(qty) < 1e-12:
                continue
            avg = float(payload.get("avg_price") or 0)
            mark = _last_mark(demo_dir, inst) if demo_dir else None
            # Prefer trade unrealized mark from summary trades if present.
            out.append(
                OpenBook(
                    demo=demo,
                    strategy_id=sid,
                    instrument=inst,
                    open_qty=qty,
                    avg_price=avg,
                    mark=mark,
                    source="oanda",
                )
            )
    return out


def _adverse_pts(qty: float, avg_price: float, mark: Optional[float]) -> float:
    if mark is None or avg_price <= 0:
        return 0.0
    # Long qty>0: adverse = avg - mark; short qty<0: adverse = mark - avg
    if qty > 0:
        return max(0.0, float(avg_price) - float(mark))
    return max(0.0, float(mark) - float(avg_price))


def _usd_est(instrument: str, pts: float, qty: float, mark: Optional[float]) -> float:
    pv = float(POINT_VALUES.get(instrument, 1.0) or 1.0)
    units = abs(float(qty))
    # Research POINT_VALUES assume ~1 standard lot for FX. Live practice uses tiny
    # OANDA units (1 unit ≈ $1 notional for FX). Prefer OANDA-style: units * pts
    # for USD-quoted; for JPY-quoted divide by mark.
    if instrument in {"USDJPY", "AUDJPY"} and mark and mark > 0:
        return units * pts / float(mark)
    if instrument in {"EURUSD", "GBPUSD", "XAUUSD", "XAGUSD", "US30", "NAS100", "SPX500"}:
        # Live practice: treat unit PnL ≈ pts * units (index CFDs $1/pt; FX micro).
        # Keep research PV only as optional note — shadow compares pts first.
        return units * pts
    return units * pts * pv


def evaluate_once(
    *,
    thresholds: Dict[str, BookThreshold],
    use_oanda: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (action_rows, status_rows)."""
    opens = _local_open_books()
    if use_oanda:
        oanda_opens = _oanda_open_books()
        # Prefer OANDA ownership when present for same demo/instrument.
        by_key = {(o.demo, o.instrument): o for o in opens}
        for o in oanda_opens:
            by_key[(o.demo, o.instrument)] = o
        opens = list(by_key.values())

    thr_by_demo = thresholds
    thr_by_sid = {t.strategy_id: t for t in thresholds.values()}

    actions: List[Dict[str, Any]] = []
    status: List[Dict[str, Any]] = []
    ts = _iso()

    if not opens:
        status.append(
            {
                "ts": ts,
                "demo": "*",
                "strategy_id": "*",
                "instrument": "*",
                "mode": "shadow",
                "open_qty": 0,
                "avg_price": "",
                "mark": "",
                "adverse_pts": 0,
                "adverse_usd_est": 0,
                "threshold_pts": "",
                "threshold_usd_est": "",
                "threshold_source": "avg_loss",
                "breach": False,
                "would_action": "heartbeat_flat",
                "detail": "no open OANDA-demo positions",
            }
        )
        return actions, status

    for book in opens:
        thr = thr_by_demo.get(book.demo) or thr_by_sid.get(book.strategy_id)
        adverse = _adverse_pts(book.open_qty, book.avg_price, book.mark)
        if thr is None or not (thr.avg_loss_pts == thr.avg_loss_pts) or thr.avg_loss_pts <= 0:
            threshold_pts = float("nan")
            src = "missing_threshold"
        else:
            # Scale-aware in dollars; points threshold is per-unit (scale-free).
            threshold_pts = float(thr.avg_loss_pts)
            src = thr.threshold_source
        breach = bool(threshold_pts == threshold_pts and adverse >= threshold_pts - 1e-12)
        adv_usd = _usd_est(book.instrument, adverse, book.open_qty, book.mark)
        thr_usd = (
            _usd_est(book.instrument, threshold_pts, book.open_qty, book.mark)
            if threshold_pts == threshold_pts
            else float("nan")
        )
        would = (
            "would_freeze_entries+would_close_tagged+would_stop_demo"
            if breach
            else "hold_monitor"
        )
        detail = (
            "adverse_pts %.4f >= avg_loss_pts %.4f (qty=%s scale_hint=%s source=%s)"
            % (
                adverse,
                threshold_pts if threshold_pts == threshold_pts else -1,
                book.open_qty,
                getattr(thr, "live_scale_hint", ""),
                book.source,
            )
            if breach
            else "open qty=%s adverse_pts=%.4f thr_pts=%s (%s)"
            % (book.open_qty, adverse, threshold_pts, book.source)
        )
        row = {
            "ts": ts,
            "demo": book.demo,
            "strategy_id": book.strategy_id,
            "instrument": book.instrument,
            "mode": "shadow",
            "open_qty": book.open_qty,
            "avg_price": book.avg_price,
            "mark": book.mark if book.mark is not None else "",
            "adverse_pts": round(adverse, 6),
            "adverse_usd_est": round(adv_usd, 4),
            "threshold_pts": round(threshold_pts, 6) if threshold_pts == threshold_pts else "",
            "threshold_usd_est": round(thr_usd, 4) if thr_usd == thr_usd else "",
            "threshold_source": src,
            "breach": breach,
            "would_action": would,
            "detail": detail,
        }
        status.append(row)
        if breach:
            actions.append(row)
            _progress(
                "SHADOW_BREACH %s %s qty=%s adverse_pts=%.4f thr=%.4f -> %s"
                % (book.demo, book.instrument, book.open_qty, adverse, threshold_pts, would)
            )
    return actions, status


def write_status_snapshot(thresholds: Dict[str, BookThreshold], status: List[Dict[str, Any]]) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _iso(),
        "mode": "shadow",
        "shadow_until": SHADOW_UNTIL.isoformat(),
        "threshold_basis": (
            "mixed: pXX_winner_mae where favorable else average_loss_pts"
            if any(str(t.threshold_source).endswith("_winner_mae") for t in thresholds.values())
            else "average_loss_pts"
        ),
        "n_books": len(thresholds),
        "open_rows": status,
        "thresholds": {k: asdict(v) for k, v in thresholds.items()},
    }
    (HUB / "STATUS.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    # Persist thresholds table for morning review
    rows = [asdict(v) for v in thresholds.values()]
    pd.DataFrame(rows).to_csv(HUB / "thresholds.csv", index=False)


def build_email(status: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> Tuple[str, str]:
    until = SHADOW_UNTIL.isoformat()
    n_open = sum(1 for r in status if float(r.get("open_qty") or 0) != 0)
    n_breach = len(actions)
    text_lines = [
        "potions risk-guard SHADOW armed",
        "hub: live/state/risk_guard_shadow/",
        "mode: shadow (log only — no freeze/close/stop)",
        "threshold: average loss pts (MAE/p80 pending)",
        "shadow_until: %s (~2 weeks)" % until,
        "open_books: %d" % n_open,
        "breaches_this_poll: %d" % n_breach,
        "",
    ]
    if actions:
        text_lines.append("Would-take actions:")
        for a in actions:
            text_lines.append(
                "- %s %s qty=%s adverse_pts=%s thr=%s -> %s"
                % (
                    a.get("demo"),
                    a.get("instrument"),
                    a.get("open_qty"),
                    a.get("adverse_pts"),
                    a.get("threshold_pts"),
                    a.get("would_action"),
                )
            )
    else:
        text_lines.append("No breaches. Flat or within avg-loss band.")
    text_lines.extend(
        [
            "",
            "Artifacts:",
            "- STATUS.json / thresholds.csv / actions.csv / poll_status.csv",
            "- Winner MAE + p80 carry study: live/state/oanda_winner_mae_carry/",
        ]
    )
    body = "\n".join(text_lines)

    rows_html = []
    for r in status[:40]:
        rows_html.append(
            "<tr>"
            "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            % (
                r.get("demo"),
                r.get("instrument"),
                r.get("open_qty"),
                r.get("adverse_pts"),
                r.get("threshold_pts"),
                r.get("breach"),
                r.get("would_action"),
                r.get("threshold_source"),
            )
        )
    html = """<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;line-height:1.4;color:#222">
<h2>Risk-guard shadow armed</h2>
<p><b>Mode:</b> shadow (log only) · <b>Until:</b> %s · <b>Threshold:</b> average loss pts</p>
<p>Open books this poll: <b>%d</b> · Breaches: <b>%d</b></p>
<p>Hub: <code>live/state/risk_guard_shadow/</code></p>
<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:13px">
<thead><tr>
<th>demo</th><th>inst</th><th>qty</th><th>adverse_pts</th><th>thr_pts</th><th>breach</th><th>would</th><th>src</th>
</tr></thead>
<tbody>
%s
</tbody></table>
<p style="margin-top:1em">MAE / percentile-carry analysis runs in parallel under
<code>live/state/oanda_winner_mae_carry/</code>. If p80/85/90/95 carry beats hard-stop books,
daemon threshold can switch from avg loss → recommended pXX winner MAE.</p>
</body></html>""" % (
        until,
        n_open,
        n_breach,
        "\n".join(rows_html) if rows_html else "<tr><td colspan='8'>flat / heartbeat</td></tr>",
    )
    return body, html


def run_once(*, email: bool, use_oanda: bool) -> int:
    HUB.mkdir(parents=True, exist_ok=True)
    if date.today() > SHADOW_UNTIL:
        _progress("SHADOW_EXPIRED past %s — exiting" % SHADOW_UNTIL.isoformat())
        return 0
    thresholds = load_thresholds()
    actions, status = evaluate_once(thresholds=thresholds, use_oanda=use_oanda)
    write_status_snapshot(thresholds, status)
    _append_csv(HUB / "poll_status.csv", status, ACTION_COLS)
    if actions:
        _append_csv(HUB / "actions.csv", actions, ACTION_COLS)
    _progress(
        "poll open=%d breach=%d books=%d oanda=%s"
        % (sum(1 for s in status if float(s.get("open_qty") or 0) != 0), len(actions), len(thresholds), use_oanda)
    )
    body, html = build_email(status, actions)
    (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
    (HUB / "EMAIL.html").write_text(html, encoding="utf-8")
    if email:
        send_email(
            subject="potions: risk-guard SHADOW armed (avg-loss, ~2w)",
            body=body,
            html=html,
        )
        _progress("email_sent")
    return 0


def run_loop(*, interval: int, use_oanda: bool, email_first: bool) -> int:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "pidfile").write_text(str(os.getpid()), encoding="utf-8")
    first = True
    try:
        while True:
            if date.today() > SHADOW_UNTIL:
                _progress("SHADOW_EXPIRED past %s — loop stop" % SHADOW_UNTIL.isoformat())
                break
            try:
                run_once(email=bool(email_first and first), use_oanda=use_oanda)
            except Exception:
                tb = traceback.format_exc()
                _progress("poll_error\n%s" % tb[-2000:])
            first = False
            time.sleep(max(30, int(interval)))
    finally:
        try:
            (HUB / "pidfile").unlink(missing_ok=True)
        except Exception:
            pass
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SEC)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--oanda", action="store_true", help="Also poll OANDA practice for tagged opens")
    args = ap.parse_args(argv)
    if args.loop:
        return run_loop(interval=args.interval, use_oanda=args.oanda, email_first=args.email)
    return run_once(email=args.email, use_oanda=args.oanda)


if __name__ == "__main__":
    raise SystemExit(main())
