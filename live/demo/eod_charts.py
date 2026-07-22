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


def _load_or_levels(state_root: Path) -> Tuple[Optional[float], Optional[float]]:
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

    or_high, or_low = _load_or_levels(state_root)
    fills_path = state_root / "fills.csv"
    orders_path = state_root / "orders.csv"
    pos_path = state_root / "positions.csv"
    fills = _session_fills(list(csv.DictReader(fills_path.open(encoding="utf-8"))) if fills_path.exists() else [], session)
    orders = list(csv.DictReader(orders_path.open(encoding="utf-8"))) if orders_path.exists() else []
    pos_rows = list(csv.DictReader(pos_path.open(encoding="utf-8"))) if pos_path.exists() else []
    pos = pos_rows[-1] if pos_rows else {"quantity": "0", "avg_price": "0", "realized_pnl": "0"}

    fig, ax = plt.subplots(figsize=(14, 7.2), dpi=140)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")

    if or_high is not None and or_low is not None:
        or_start = bars[0]["dt"]
        or_end = next((b["dt"] for b in bars if b["dt"].hour == 9 and b["dt"].minute >= 45), bars[min(14, len(bars) - 1)]["dt"])
        ax.axhspan(or_low, or_high, facecolor="#4a90d9", alpha=0.18, zorder=0)
        ax.axhline(or_high, color="#4a90d9", lw=1.2, ls="--", alpha=0.9, label=("OR high " + pf) % or_high)
        ax.axhline(or_low, color="#4a90d9", lw=1.2, ls="--", alpha=0.9, label=("OR low " + pf) % or_low)
        ax.axvspan(or_start, or_end, facecolor="#4a90d9", alpha=0.08, zorder=0)

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

    if abs(qty) < 1e-12:
        title_pos = "flat"
        pnl_bit = "realized≈ $%.0f" % realized_usd
    else:
        title_pos = ("%+g @ " + pf) % (qty, avg)
        pnl_bit = "uPnL≈ $%.0f" % u_pnl

    ax.set_title(
        "%s v2b ungated paper — %s   last %s   %s   (%d bars → %s)"
        % (
            instrument.upper(),
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

    ys = [b["l"] for b in bars] + [b["h"] for b in bars]
    if or_low is not None:
        ys.append(or_low)
    if or_high is not None:
        ys.append(or_high)
    for o in orders:
        px = o.get("stop_price") or o.get("limit_price")
        if px not in (None, "") and o.get("status") in {"submitted", "working", "partially_filled", "filled"}:
            if (o.get("bracket_role") or "") in {"wide_stop", "runner_stop", "tp1", "tp2", "entry"}:
                ys.append(float(px))
    for fill in fills:
        ys.append(float(fill["price"]))
    pad = (max(ys) - min(ys)) * 0.12 or 1.0
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_xlim(bars[0]["dt"], bars[-1]["dt"])

    fig.autofmt_xdate()
    fig.tight_layout()
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
