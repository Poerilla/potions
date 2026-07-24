"""EOD session position charts for Pilot A demo paper runners."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from ..replay_audit import POINT_VALUES

NY = pytz.timezone("America/New_York")
RTH_OPEN_UTC_HINT = "T13:30:00Z"  # winter EST; filtered via NY conversion below


def _parse_ny(ts: str) -> datetime:
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # OANDA timestamps can carry nanoseconds; fromisoformat (3.8) accepts ≤6 frac digits.
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


def _f(row: Dict[str, str], key: str) -> Optional[float]:
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _price_fmt(instrument: str) -> str:
    if instrument.upper() in {"EURUSD", "GBPUSD", "AUDUSD"}:
        return "%.5f"
    if instrument.upper() in {"USDJPY", "AUDJPY"}:
        return "%.3f"
    return "%.2f"  # index CFDs


def _load_rth_bars(bars_path: Path, instrument: str, session: date) -> List[Dict[str, Any]]:
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
            if dt.date() != session:
                continue
            clock = dt.timetz().replace(tzinfo=None) if dt.tzinfo else dt.time()
            if clock < dt_time(9, 30) or clock >= dt_time(16, 0):
                continue
            out.append(
                {
                    "dt": dt,
                    "o": float(row["open"]),
                    "h": float(row["high"]),
                    "l": float(row["low"]),
                    "c": float(row["close"]),
                    "bid_h": _f(row, "bid_high"),
                    "bid_l": _f(row, "bid_low"),
                    "ask_h": _f(row, "ask_high"),
                    "ask_l": _f(row, "ask_low"),
                }
            )
    return out


def _load_or_levels(state_root: Path, session: date, bars: Optional[List[Dict[str, Any]]] = None) -> Tuple[Optional[float], Optional[float]]:
    """Session-scoped opening range for charting.

    Prefer reconstructing from session RTH bars 09:30–09:45 (same mid OHLC the
    chart plots), then ``levels.csv`` ``v2b_or_*`` for ``session``, then (only if
    ``session`` is today) live strategy_state.
    """

    if bars:
        or_bars = [
            b
            for b in bars
            if b["dt"].timetz().replace(tzinfo=None) >= dt_time(9, 30)
            and b["dt"].timetz().replace(tzinfo=None) < dt_time(9, 45)
        ]
        if or_bars:
            return max(b["h"] for b in or_bars), min(b["l"] for b in or_bars)

    levels_path = state_root / "levels.csv"
    if levels_path.exists():
        by_ts: Dict[str, Dict[str, float]] = {}
        with levels_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                name = (row.get("level_name") or "").strip()
                if name not in {"v2b_or_high", "v2b_or_low"}:
                    continue
                ts = row.get("active_from") or ""
                try:
                    dt = _parse_ny(ts)
                except Exception:
                    continue
                if dt.date() != session:
                    continue
                px = _f(row, "price")
                if px is None:
                    continue
                slot = by_ts.setdefault(ts, {})
                if name == "v2b_or_high":
                    slot["high"] = px
                else:
                    slot["low"] = px
        finalized: Optional[Tuple[float, float]] = None
        last_complete: Optional[Tuple[float, float]] = None
        for ts in sorted(by_ts.keys()):
            slot = by_ts[ts]
            if "high" not in slot or "low" not in slot:
                continue
            pair = (slot["high"], slot["low"])
            last_complete = pair
            try:
                clock = _parse_ny(ts).timetz().replace(tzinfo=None)
            except Exception:
                clock = dt_time(0, 0)
            if clock >= dt_time(9, 45) and finalized is None:
                finalized = pair
        if finalized is not None:
            return finalized
        if last_complete is not None:
            return last_complete

    today = datetime.now(tz=NY).date()
    if session != today:
        return None, None
    path = state_root / "strategy_state.csv"
    if not path.exists():
        return None, None
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return None, None
    try:
        state = json.loads(rows[-1].get("state_json") or "{}")
    except json.JSONDecodeError:
        return None, None
    oh, ol = state.get("or_high"), state.get("or_low")
    try:
        return (float(oh) if oh is not None else None, float(ol) if ol is not None else None)
    except (TypeError, ValueError):
        return None, None


def _session_fills(fills: List[Dict[str, str]], session: date) -> List[Dict[str, str]]:
    out = []
    for row in fills:
        ts = row.get("ts") or ""
        try:
            if _parse_ny(ts).date() == session:
                out.append(row)
        except Exception:
            continue
    return out


def _session_orders(orders: List[Dict[str, str]], session: date, fills: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Keep orders belonging to this session's trade(s), not later days' working book."""

    trade_ids = {f.get("trade_id") for f in fills if f.get("trade_id")}
    session_tag = session.strftime("%Y%m%d")
    out: List[Dict[str, str]] = []
    for row in orders:
        tid = str(row.get("trade_id") or "")
        if trade_ids and tid in trade_ids:
            out.append(row)
            continue
        if session_tag and session_tag in tid:
            out.append(row)
            continue
        for key in ("live_after_ts", "created_at", "updated_at"):
            raw = row.get(key) or ""
            if not raw:
                continue
            try:
                if _parse_ny(raw).date() == session:
                    out.append(row)
                    break
            except Exception:
                continue
    return out


def _session_position_snapshot(
    fills: List[Dict[str, str]],
    pos_rows: List[Dict[str, str]],
    session: date,
) -> Dict[str, str]:
    """Position overlay for the charted session (not always the live book)."""

    today = datetime.now(tz=NY).date()
    if session == today and pos_rows:
        return pos_rows[-1]

    qty = 0.0
    avg = 0.0
    realized = 0.0
    # Reconstruct rough open qty from session fills (entry +, reduce -).
    for f in fills:
        side = (f.get("side") or "").lower()
        q = float(f.get("quantity") or 0)
        signed = q if side == "buy" else -q
        reason = (f.get("reason") or "").strip()
        if reason == "entry":
            qty = signed
            avg = float(f.get("price") or 0)
        else:
            # reduce toward flat
            if qty > 0:
                qty = max(0.0, qty - q)
            elif qty < 0:
                qty = min(0.0, qty + q)
    return {"quantity": str(qty), "avg_price": str(avg), "realized_pnl": str(realized)}


def write_session_position_chart(
    output_root: Path,
    instrument: str,
    *,
    session_date: Optional[str] = None,
    point_value: Optional[float] = None,
) -> Optional[Path]:
    """Write ``charts/{instrument_lower}_v2b_position_YYYY-MM-DD.png`` for NY RTH.

    Returns the output path, or ``None`` when there are no RTH bars to chart.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    output_root = Path(output_root)
    state_root = output_root / "state"
    out_dir = output_root / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    if session_date:
        session = date.fromisoformat(session_date)
    else:
        session = datetime.now(tz=NY).date()

    bars_path = state_root / "bars" / ("%s_1m.csv" % instrument.upper())
    bars = _load_rth_bars(bars_path, instrument, session)
    if not bars:
        return None

    pf = _price_fmt(instrument)
    pv = float(point_value if point_value is not None else POINT_VALUES.get(instrument.upper(), 1.0))

    or_high, or_low = _load_or_levels(state_root, session, bars)
    fills_path = state_root / "fills.csv"
    orders_path = state_root / "orders.csv"
    pos_path = state_root / "positions.csv"
    fills = _session_fills(list(csv.DictReader(fills_path.open(encoding="utf-8"))) if fills_path.exists() else [], session)
    all_orders = list(csv.DictReader(orders_path.open(encoding="utf-8"))) if orders_path.exists() else []
    orders = _session_orders(all_orders, session, fills)
    pos_rows = list(csv.DictReader(pos_path.open(encoding="utf-8"))) if pos_path.exists() else []
    pos = _session_position_snapshot(fills, pos_rows, session)

    fig, ax = plt.subplots(figsize=(14, 7.2), dpi=140)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")

    if or_high is not None and or_low is not None:
        or_start = next(
            (b["dt"] for b in bars if b["dt"].hour == 9 and b["dt"].minute == 30),
            bars[0]["dt"],
        )
        or_end = next(
            (b["dt"] for b in bars if b["dt"].hour == 9 and b["dt"].minute >= 45),
            bars[min(14, len(bars) - 1)]["dt"],
        )
        # Classic OR box on the 09:30–09:45 window (not a full-height time strip /
        # full-width band — those made the range look paper-thin or invisible).
        x0 = mdates.date2num(or_start)
        x1 = mdates.date2num(or_end)
        ax.add_patch(
            plt.Rectangle(
                (x0, or_low),
                max(x1 - x0, 1e-9),
                or_high - or_low,
                facecolor="#4a90d9",
                edgecolor="#7eb6e8",
                linewidth=1.6,
                alpha=0.28,
                zorder=0,
                label=("OR box %s–%s" % (pf % or_low, pf % or_high)),
            )
        )
        ax.axhline(or_high, color="#4a90d9", lw=1.3, ls="--", alpha=0.95, label=("OR high " + pf) % or_high)
        ax.axhline(or_low, color="#4a90d9", lw=1.3, ls="--", alpha=0.95, label=("OR low " + pf) % or_low)
    else:
        first_clock = bars[0]["dt"].timetz().replace(tzinfo=None)
        if first_clock > dt_time(9, 45):
            ax.text(
                0.01,
                0.98,
                "OR n/a — no 09:30–09:45 bars (session data starts %s ET)"
                % bars[0]["dt"].strftime("%H:%M"),
                transform=ax.transAxes,
                va="top",
                ha="left",
                color="#f0c674",
                fontsize=9,
                fontweight="bold",
                zorder=8,
            )

    have_q = [b for b in bars if b["bid_l"] is not None and b["ask_h"] is not None]
    if have_q:
        xs = [mdates.date2num(b["dt"]) for b in have_q]
        ax.fill_between(
            xs,
            [b["bid_l"] for b in have_q],
            [b["ask_h"] for b in have_q],
            color="#c4a35a",
            alpha=0.22,
            linewidth=0,
            label="bid–ask envelope",
            zorder=1,
        )

    # ~0.7 minute candle body in matplotlib date units
    width = 0.0005
    for b in bars:
        x = mdates.date2num(b["dt"])
        up = b["c"] >= b["o"]
        color = "#3dcc91" if up else "#e85d5d"
        ax.vlines(x, b["l"], b["h"], color=color, lw=1.0, zorder=3)
        bottom = min(b["o"], b["c"])
        height = abs(b["c"] - b["o"]) or (abs(b["h"] - b["l"]) * 0.01) or 1e-9
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                zorder=4,
            )
        )

    reason_colors = {
        "entry": "#ffcc33",
        "tp1": "#7ec8ff",
        "tp2": "#9bdbff",
        "eod_close": "#d0a0ff",
        "wide_stop": "#ff8a7a",
        "runner_stop": "#ff8a7a",
        "stop": "#ff8a7a",
    }
    for i, fill in enumerate(fills):
        ft = _parse_ny(fill["ts"])
        price = float(fill["price"])
        side = fill["side"]
        qty = fill["quantity"]
        reason = (fill.get("reason") or "").strip() or ("entry" if i == 0 else "fill")
        marker = "v" if side == "sell" else "^"
        color = reason_colors.get(reason, "#7ec8ff")
        label = ("%s %s × %s @ " + pf) % (reason, side, qty, price)
        ax.scatter(
            [ft],
            [price],
            marker=marker,
            s=140,
            color=color,
            edgecolors="#111",
            linewidths=0.8,
            zorder=6,
            label=label,
        )
        if reason == "entry":
            tag = "SHORT" if side == "sell" else "LONG"
            ax.annotate(
                ("%s entry\n%s × %s\n@ " + pf) % (tag, side, qty, price),
                xy=(ft, price),
                xytext=(12, 28),
                textcoords="offset points",
                color="#ffcc33",
                fontsize=9,
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#ffcc33", lw=1.0),
                zorder=7,
            )
        elif reason in {"tp1", "tp2", "eod_close"}:
            ax.annotate(
                ("%s\n%s × %s @ " + pf) % (reason.upper(), side, qty, price),
                xy=(ft, price),
                xytext=(10, -36 if reason != "eod_close" else 24),
                textcoords="offset points",
                color=color,
                fontsize=8,
                fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=color, lw=0.9),
                zorder=7,
            )

    role_styles = {
        "wide_stop": ("#e85d5d", "-", "SL"),
        "runner_stop": ("#e85d5d", "-", "runner SL"),
        "tp1": ("#3dcc91", "-.", "TP1"),
        "tp2": ("#2aa87a", ":", "TP2"),
    }
    for o in orders:
        role = o.get("bracket_role") or ""
        px = o.get("stop_price") or o.get("limit_price")
        if px in (None, ""):
            continue
        px_f = float(px)
        status = o.get("status")
        if status in {"submitted", "working", "partially_filled"}:
            color, ls, tag = role_styles.get(role, ("#bbbbbb", "--", role or o.get("order_type") or "order"))
            ax.axhline(
                px_f,
                color=color,
                lw=1.4,
                ls=ls,
                alpha=0.95,
                label=("%s %s @ " + pf + " (qty %s)") % (tag, o.get("order_type"), px_f, o.get("quantity")),
            )
        elif status == "filled" and role in role_styles:
            color, ls, tag = role_styles[role]
            ax.axhline(px_f, color=color, lw=1.0, ls=ls, alpha=0.35, label=("%s filled @ " + pf) % (tag, px_f))
        elif status == "cancelled" and role in {"tp1", "tp2", "wide_stop", "runner_stop"}:
            # Ghost the cancelled bracket so the chart still shows what was working.
            color, ls, tag = role_styles.get(role, ("#bbbbbb", "--", role))
            ax.axhline(
                px_f,
                color=color,
                lw=0.9,
                ls=ls,
                alpha=0.22,
                label=("%s cancelled @ " + pf) % (tag, px_f),
            )

    entry_fill = next((f for f in fills if (f.get("reason") or "") == "entry"), fills[0] if fills else None)
    if entry_fill:
        entry_px = float(entry_fill["price"])
        entry_t = _parse_ny(entry_fill["ts"])
        ax.plot([entry_t, bars[-1]["dt"]], [entry_px, entry_px], color="#ffcc33", lw=1.0, ls=":", alpha=0.7, zorder=5)

    qty = float(pos.get("quantity") or 0)
    avg = float(pos.get("avg_price") or 0)
    last = bars[-1]["c"]
    realized_pts = float(pos.get("realized_pnl") or 0)
    realized_usd = realized_pts * pv
    if qty < 0:
        u_pnl = (avg - last) * abs(qty) * pv
    elif qty > 0:
        u_pnl = (last - avg) * abs(qty) * pv
    else:
        u_pnl = 0.0

    book = "oanda" if "oanda" in output_root.name.lower() else "paper"
    if abs(qty) < 1e-12:
        title_pos = "flat"
        # Prefer session FIFO realized when flat (local positions.csv can lag / disagree).
        try:
            from .session_pnl import fifo_pnl_from_fills

            _raw, realized_usd = fifo_pnl_from_fills(fills, instrument)
        except Exception:
            realized_usd = realized_pts * pv
        pnl_bit = "realized≈ $%.0f" % realized_usd
    else:
        title_pos = ("%+g @ " + pf) % (qty, avg)
        pnl_bit = "uPnL≈ $%.0f" % u_pnl

    ax.set_title(
        "%s v2b ungated %s — %s   last %s   %s   (%d bars → %s)"
        % (
            instrument.upper(),
            book,
            title_pos,
            pf % last,
            pnl_bit,
            len(bars),
            bars[-1]["dt"].strftime("%H:%M ET"),
        ),
        color="#e8eef5",
        fontsize=11,
        pad=12,
    )
    ax.set_ylabel("Mid price", color="#c5d0db")
    ax.set_xlabel("America/New_York", color="#c5d0db")
    ax.tick_params(colors="#9aa7b5")
    for spine in ax.spines.values():
        spine.set_color("#2a3540")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=NY))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=list(range(0, 60, 15)), tz=NY))
    ax.grid(True, color="#1c2630", lw=0.6)
    ax.legend(
        loc="upper left",
        fontsize=8,
        framealpha=0.85,
        facecolor="#1a222b",
        edgecolor="#2a3540",
        labelcolor="#e8eef5",
    )

    # Y-limits: keep OR / price action readable. Distant TP/SL levels (often
    # 2R away) used to stretch the axis and make the OR look paper-thin.
    bar_lows = [b["l"] for b in bars]
    bar_highs = [b["h"] for b in bars]
    core = bar_lows + bar_highs
    if or_low is not None:
        core.append(or_low)
    if or_high is not None:
        core.append(or_high)
    for fill in fills:
        core.append(float(fill["price"]))
    core_lo, core_hi = min(core), max(core)
    core_span = (core_hi - core_lo) or 1.0
    # Allow nearby working levels (e.g. stop at OR extreme) but not far TPs.
    near_pad = core_span * 0.35
    ys = list(core)
    offchart: List[str] = []
    for o in orders:
        px = o.get("stop_price") or o.get("limit_price")
        if px in (None, ""):
            continue
        if o.get("status") not in {"submitted", "working", "partially_filled", "filled"}:
            continue
        role = o.get("bracket_role") or ""
        if role not in {"wide_stop", "runner_stop", "tp1", "tp2", "entry"}:
            continue
        px_f = float(px)
        if (core_lo - near_pad) <= px_f <= (core_hi + near_pad):
            ys.append(px_f)
        else:
            offchart.append(("%s @ " + pf) % (role, px_f))
    y_lo = min(ys) - ((max(ys) - min(ys)) * 0.12 or 1.0)
    y_hi = max(ys) + ((max(ys) - min(ys)) * 0.12 or 1.0)
    ax.set_xlim(bars[0]["dt"], bars[-1]["dt"])
    if offchart:
        ax.text(
            0.99,
            0.02,
            "off-scale: " + ", ".join(offchart[:4]),
            transform=ax.transAxes,
            va="bottom",
            ha="right",
            color="#9aa7b5",
            fontsize=8,
            zorder=8,
        )

    fig.autofmt_xdate()
    fig.tight_layout()
    # Re-apply after layout/autoscale so distant TP lines cannot squash the OR.
    ax.set_ylim(y_lo, y_hi)
    ax.set_autoscale_on(False)
    out = out_dir / ("%s_v2b_position_%s.png" % (instrument.lower(), session.isoformat()))
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def maybe_write_eod_chart(
    output_root: Path,
    instrument: str,
    *,
    session_date: str,
    point_value: Optional[float] = None,
    log: Optional[Any] = None,
) -> Optional[Path]:
    """Best-effort EOD chart; never raises into the stream loop."""
    try:
        out = write_session_position_chart(
            output_root,
            instrument,
            session_date=session_date,
            point_value=point_value,
        )
        if log is not None:
            if out is None:
                log(output_root, "EOD chart skipped — no RTH bars for %s %s" % (instrument, session_date))
            else:
                log(output_root, "EOD chart wrote %s" % out)
        return out
    except Exception as exc:
        if log is not None:
            log(output_root, "EOD chart failed for %s: %s: %s" % (instrument, type(exc).__name__, exc))
        return None
