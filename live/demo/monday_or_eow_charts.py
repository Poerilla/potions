"""Friday end-of-week chart packs for Monday OR demo runners.

Writes under ``<output_root>/charts/``:

- ``{instr}_monday_or_week_{week_monday}.png`` — Mon–Fri overview + all week fills
- ``{instr}_monday_or_trade_{trade_id}_{entry_ymd}.png`` — one PNG per trade that week

Triggered by the daemon at Friday ≥ 15:59 America/New_York (same gate as FILE_SIZES).
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz

from .eod_charts import _parse_ny, _price_fmt

NY = pytz.timezone("America/New_York")
WEEK_END_NY = dt_time(15, 59)


def week_monday_for(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _load_strategy_or(state_root: Path, week_monday: date) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    path = state_root / "strategy_state.csv"
    if not path.exists():
        return None, None, None
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return None, None, None
    try:
        state = json.loads(rows[-1].get("state_json") or "{}")
    except json.JSONDecodeError:
        return None, None, None
    wm = str(state.get("week_monday") or "")
    if wm and wm != week_monday.isoformat():
        # State already rolled to a newer week — still prefer stored levels only when matching.
        return None, None, None
    try:
        mh = float(state["mon_high"]) if state.get("mon_high") not in (None, "") else None
        ml = float(state["mon_low"]) if state.get("mon_low") not in (None, "") else None
        r = float(state["R"]) if state.get("R") not in (None, "") else None
    except (TypeError, ValueError, KeyError):
        return None, None, None
    return mh, ml, r


def _load_15m_week(bars_path: Path, week_monday: date) -> List[Dict[str, Any]]:
    if not bars_path.exists():
        return []
    start = NY.localize(datetime.combine(week_monday, dt_time(0, 0)))
    end = start + timedelta(days=5)  # through Friday close window
    end = end.replace(hour=16, minute=0, second=0, microsecond=0)
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


def _or_from_monday_bars(bars: List[Dict[str, Any]], week_monday: date) -> Tuple[Optional[float], Optional[float]]:
    mon = [b for b in bars if b["dt"].date() == week_monday]
    if not mon:
        return None, None
    return max(b["h"] for b in mon), min(b["l"] for b in mon)


def _week_fills(fills: List[Dict[str, str]], week_monday: date) -> List[Dict[str, str]]:
    start = week_monday
    end = week_monday + timedelta(days=5)
    out: List[Dict[str, str]] = []
    for row in fills:
        ts = row.get("ts") or ""
        try:
            d = _parse_ny(ts).date()
        except Exception:
            continue
        if start <= d < end:
            out.append(row)
    return out


def _group_trades(fills: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, List[Dict[str, str]]] = {}
    for row in fills:
        tid = str(row.get("trade_id") or "").strip() or "_none"
        by_id.setdefault(tid, []).append(row)
    trades: List[Dict[str, Any]] = []
    for tid, rows in by_id.items():
        rows = sorted(rows, key=lambda r: r.get("ts") or "")
        entry = next((r for r in rows if (r.get("reason") or "") == "entry"), rows[0])
        exits = [r for r in rows if (r.get("reason") or "") != "entry"]
        last = exits[-1] if exits else entry
        side = "long" if (entry.get("side") or "").lower() == "buy" else "short"
        trades.append(
            {
                "trade_id": tid,
                "side": side,
                "entry": entry,
                "fills": rows,
                "exit": last if exits else None,
                "entry_ts": entry.get("ts") or "",
                "entry_price": float(entry.get("price") or 0),
            }
        )
    trades.sort(key=lambda t: t["entry_ts"])
    return trades


def _draw_candles(ax, bars: List[Dict[str, Any]], *, width: float) -> None:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    for b in bars:
        x = mdates.date2num(b["dt"])
        up = b["c"] >= b["o"]
        color = "#3dcc91" if up else "#e85d5d"
        ax.vlines(x, b["l"], b["h"], color=color, lw=0.7, zorder=3)
        bottom = min(b["o"], b["c"])
        height = abs(b["c"] - b["o"]) or (abs(b["h"] - b["l"]) * 0.01) or 1e-9
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.4,
                zorder=4,
            )
        )


def _style_ax(ax, *, title: str) -> None:
    import matplotlib.dates as mdates

    ax.set_title(title, color="#e8eef5", fontsize=11, pad=10)
    ax.set_ylabel("Mid price", color="#c5d0db")
    ax.set_xlabel("America/New_York", color="#c5d0db")
    ax.tick_params(colors="#9aa7b5")
    for spine in ax.spines.values():
        spine.set_color("#2a3540")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=NY))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=NY))
    ax.grid(True, color="#1c2630", lw=0.6)
    ax.legend(
        loc="upper left",
        fontsize=7,
        ncol=2,
        framealpha=0.85,
        facecolor="#1a222b",
        edgecolor="#2a3540",
        labelcolor="#e8eef5",
    )


def write_week_overview_chart(
    output_root: Path,
    instrument: str,
    *,
    week_monday: date,
    point_value: Optional[float] = None,  # reserved
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    _ = point_value
    output_root = Path(output_root)
    state_root = output_root / "state"
    out_dir = output_root / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    bars_path = state_root / "bars" / ("%s_15m.csv" % instrument.upper())
    bars = _load_15m_week(bars_path, week_monday)
    if not bars:
        return None

    pf = _price_fmt(instrument)
    mon_high, mon_low, R = _load_strategy_or(state_root, week_monday)
    if mon_high is None or mon_low is None:
        mon_high, mon_low = _or_from_monday_bars(bars, week_monday)
        if mon_high is not None and mon_low is not None:
            R = mon_high - mon_low

    fills_path = state_root / "fills.csv"
    all_fills = list(csv.DictReader(fills_path.open(encoding="utf-8"))) if fills_path.exists() else []
    fills = _week_fills(all_fills, week_monday)
    trades = _group_trades(fills)

    fig, ax = plt.subplots(figsize=(16, 7.2), dpi=130)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")

    if mon_high is not None and mon_low is not None:
        ax.axhspan(mon_low, mon_high, color="#4a90d9", alpha=0.18, zorder=0, label="Monday OR")
        ax.axhline(mon_high, color="#4a90d9", lw=1.2, ls="--", alpha=0.95, label=("OR high " + pf) % mon_high)
        ax.axhline(mon_low, color="#4a90d9", lw=1.2, ls="--", alpha=0.95, label=("OR low " + pf) % mon_low)

    _draw_candles(ax, bars, width=0.008)

    reason_colors = {
        "entry": "#ffcc33",
        "dd30": "#ff9f6b",
        "dd50": "#ff8a7a",
        "stop": "#ff8a7a",
        "target": "#7ec8ff",
        "week_end": "#d0a0ff",
        "flatten": "#d0a0ff",
    }
    for fill in fills:
        ft = _parse_ny(fill["ts"])
        price = float(fill["price"])
        side = (fill.get("side") or "").lower()
        reason = (fill.get("reason") or "").strip() or "fill"
        marker = "v" if side == "sell" else "^"
        color = reason_colors.get(reason, "#7ec8ff")
        ax.scatter(
            [ft],
            [price],
            marker=marker,
            s=90,
            color=color,
            edgecolors="#111",
            linewidths=0.6,
            zorder=6,
            label=("%s %s @ " + pf) % (reason, side, price),
        )

    realized = 0.0
    try:
        from .session_pnl import fifo_pnl_from_fills

        _raw, realized = fifo_pnl_from_fills(fills, instrument)
    except Exception:
        realized = 0.0

    book = "oanda" if "oanda" in output_root.name.lower() else "paper"
    r_bit = (" R=" + pf) % R if R else ""
    title = "%s Monday OR %s — week of %s%s   trades=%d fills=%d   realized≈ $%.0f" % (
        instrument.upper(),
        book,
        week_monday.isoformat(),
        r_bit,
        len(trades),
        len(fills),
        realized,
    )
    _style_ax(ax, title=title)
    ax.set_xlim(bars[0]["dt"], bars[-1]["dt"])
    ys = [b["l"] for b in bars] + [b["h"] for b in bars]
    if mon_low is not None:
        ys.append(mon_low)
    if mon_high is not None:
        ys.append(mon_high)
    for f in fills:
        ys.append(float(f["price"]))
    span = (max(ys) - min(ys)) or 1.0
    ax.set_ylim(min(ys) - span * 0.08, max(ys) + span * 0.08)

    fig.autofmt_xdate()
    fig.tight_layout()
    out = out_dir / ("%s_monday_or_week_%s.png" % (instrument.lower(), week_monday.isoformat()))
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def write_trade_chart(
    output_root: Path,
    instrument: str,
    trade: Dict[str, Any],
    *,
    week_monday: date,
    mon_high: Optional[float],
    mon_low: Optional[float],
    R: Optional[float],
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_root = Path(output_root)
    state_root = output_root / "state"
    out_dir = output_root / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)

    bars_path = state_root / "bars" / ("%s_15m.csv" % instrument.upper())
    bars = _load_15m_week(bars_path, week_monday)
    if not bars:
        return None

    pf = _price_fmt(instrument)
    entry = trade["entry"]
    entry_ts = _parse_ny(trade["entry_ts"])
    entry_px = float(trade["entry_price"])
    side = trade["side"]
    fills = trade["fills"]
    tid = str(trade["trade_id"])
    tid_short = tid[-8:] if len(tid) > 8 else tid
    entry_ymd = entry_ts.date().isoformat()

    fig, ax = plt.subplots(figsize=(16, 7.0), dpi=130)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")

    if mon_high is not None and mon_low is not None:
        ax.axhspan(mon_low, mon_high, color="#4a90d9", alpha=0.18, zorder=0, label="Monday OR")
        ax.axhline(mon_high, color="#4a90d9", lw=1.1, ls="--", alpha=0.9)
        ax.axhline(mon_low, color="#4a90d9", lw=1.1, ls="--", alpha=0.9)

    r = float(R) if R not in (None, 0) else (
        (mon_high - mon_low) if mon_high is not None and mon_low is not None else None
    )
    if r and r > 0:
        if side == "long":
            stop, target = entry_px - r, entry_px + 2.0 * r
            dd30, dd50 = entry_px - 0.30 * r, entry_px - 0.50 * r
        else:
            stop, target = entry_px + r, entry_px - 2.0 * r
            dd30, dd50 = entry_px + 0.30 * r, entry_px + 0.50 * r
        ax.axhline(stop, color="#e85d5d", lw=1.1, ls=":", alpha=0.9, label=("stop 1R " + pf) % stop)
        ax.axhline(target, color="#7ec8ff", lw=1.1, ls=":", alpha=0.9, label=("target 2R " + pf) % target)
        ax.axhline(dd30, color="#ff9f6b", lw=0.9, ls="-.", alpha=0.75, label=("DD30 " + pf) % dd30)
        ax.axhline(dd50, color="#ff8a7a", lw=0.9, ls="-.", alpha=0.75, label=("DD50 " + pf) % dd50)

    _draw_candles(ax, bars, width=0.008)

    reason_colors = {
        "entry": "#ffcc33",
        "dd30": "#ff9f6b",
        "dd50": "#ff8a7a",
        "stop": "#ff8a7a",
        "target": "#7ec8ff",
        "week_end": "#d0a0ff",
        "flatten": "#d0a0ff",
    }
    for fill in fills:
        ft = _parse_ny(fill["ts"])
        price = float(fill["price"])
        side_f = (fill.get("side") or "").lower()
        reason = (fill.get("reason") or "").strip() or "fill"
        marker = "v" if side_f == "sell" else "^"
        color = reason_colors.get(reason, "#7ec8ff")
        ax.scatter(
            [ft],
            [price],
            marker=marker,
            s=110,
            color=color,
            edgecolors="#111",
            linewidths=0.7,
            zorder=6,
            label=("%s %s × %s @ " + pf) % (reason, side_f, fill.get("quantity"), price),
        )

    exit_fill = trade.get("exit")
    if exit_fill is not None:
        exit_ts = _parse_ny(exit_fill["ts"])
        ax.axvspan(entry_ts, exit_ts, color="#3dcc91", alpha=0.08, zorder=0)

    book = "oanda" if "oanda" in output_root.name.lower() else "paper"
    _style_ax(
        ax,
        title="%s Monday OR %s — %s %s  entry %s @ %s"
        % (instrument.upper(), book, side, tid_short, entry_ymd, pf % entry_px),
    )
    ax.set_xlim(bars[0]["dt"], bars[-1]["dt"])
    ys = [b["l"] for b in bars] + [b["h"] for b in bars] + [float(f["price"]) for f in fills]
    if mon_low is not None:
        ys.append(mon_low)
    if mon_high is not None:
        ys.append(mon_high)
    span = (max(ys) - min(ys)) or 1.0
    ax.set_ylim(min(ys) - span * 0.08, max(ys) + span * 0.08)

    fig.autofmt_xdate()
    fig.tight_layout()
    out = out_dir / ("%s_monday_or_trade_%s_%s.png" % (instrument.lower(), tid_short, entry_ymd))
    fig.savefig(out, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out


def write_eow_chart_pack(
    output_root: Path,
    instrument: str,
    *,
    as_of: Optional[date] = None,
    point_value: Optional[float] = None,
) -> List[Path]:
    """Write week overview + per-trade charts for the ISO week containing ``as_of`` (default: today NY)."""

    as_of = as_of or datetime.now(tz=NY).date()
    week_monday = week_monday_for(as_of)
    written: List[Path] = []

    overview = write_week_overview_chart(
        output_root, instrument, week_monday=week_monday, point_value=point_value
    )
    if overview is not None:
        written.append(overview)

    state_root = Path(output_root) / "state"
    mon_high, mon_low, R = _load_strategy_or(state_root, week_monday)
    fills_path = state_root / "fills.csv"
    all_fills = list(csv.DictReader(fills_path.open(encoding="utf-8"))) if fills_path.exists() else []
    fills = _week_fills(all_fills, week_monday)
    if mon_high is None or mon_low is None:
        bars = _load_15m_week(state_root / "bars" / ("%s_15m.csv" % instrument.upper()), week_monday)
        mon_high, mon_low = _or_from_monday_bars(bars, week_monday)
        if mon_high is not None and mon_low is not None:
            R = mon_high - mon_low

    for trade in _group_trades(fills):
        path = write_trade_chart(
            output_root,
            instrument,
            trade,
            week_monday=week_monday,
            mon_high=mon_high,
            mon_low=mon_low,
            R=R,
        )
        if path is not None:
            written.append(path)
    return written


def maybe_write_eow_chart_pack(
    output_root: Path,
    instrument: str,
    *,
    as_of: Optional[date] = None,
    point_value: Optional[float] = None,
    log: Optional[Any] = None,
) -> List[Path]:
    """Best-effort Friday EOW pack; never raises into the stream loop."""
    try:
        written = write_eow_chart_pack(
            output_root, instrument, as_of=as_of, point_value=point_value
        )
        if log is not None:
            if not written:
                log(
                    output_root,
                    "EOW Monday OR chart pack skipped — no 15m bars for %s week of %s"
                    % (instrument, week_monday_for(as_of or datetime.now(tz=NY).date()).isoformat()),
                )
            else:
                log(
                    output_root,
                    "EOW Monday OR chart pack wrote %d file(s): %s"
                    % (len(written), ", ".join(p.name for p in written)),
                )
        return written
    except Exception as exc:
        if log is not None:
            log(
                output_root,
                "EOW Monday OR chart pack failed for %s: %s: %s"
                % (instrument, type(exc).__name__, exc),
            )
        return []
