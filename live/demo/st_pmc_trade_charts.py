"""Trade / open-position charts for hourly ST+PMC demo runners.

Emits under ``<output_root>/charts/`` only when there is trade activity:

- ``{instr}_st_pmc_trade_{trade_id}_{entry_ymd}.png`` — once per completed trade
- ``{instr}_st_pmc_open_{trade_id}_{entry_ymd}.png`` — refreshed while qty ≠ 0

Call ``maybe_update_st_pmc_charts`` from the daemon heartbeat (throttled open refresh).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytz

from .eod_charts import _parse_ny, _price_fmt

NY = pytz.timezone("America/New_York")
OPEN_CHART_MIN_SECONDS = 900  # refresh open overlay at most every 15m


def _tid_short(trade_id: str) -> str:
    """Prefer ``oanda_t7`` / ``paper_t1`` over a raw trailing slice."""
    tid = str(trade_id or "").strip()
    if not tid:
        return "unknown"
    idx = tid.rfind("_t")
    if idx >= 0:
        prev = tid.rfind("_", 0, idx)
        if prev >= 0 and tid[prev + 1 : idx] in {"oanda", "paper"}:
            return tid[prev + 1 :]
        return tid[idx + 1 :]
    return tid[-12:] if len(tid) > 12 else tid


EXIT_REASONS = {
    "stop",
    "target",
    "tp1",
    "tp2",
    "runner_stop",
    "wide_stop",
    "eod",
    "flatten",
    "close",
    "year_end_flatten",
}
ENTRY_REASONS = {"entry", "add", "retest_add", "bb_add", "runner_entry"}


def _load_bars_range(
    bars_path: Path,
    *,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
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
            if dt < start or dt > end:
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


def _draw_candles(ax, bars: List[Dict[str, Any]], *, width: float) -> None:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    for b in bars:
        x = mdates.date2num(b["dt"])
        up = b["c"] >= b["o"]
        color = "#3dcc91" if up else "#e85d5d"
        ax.vlines(x, b["l"], b["h"], color=color, lw=0.6, zorder=3)
        bottom = min(b["o"], b["c"])
        height = abs(b["c"] - b["o"]) or (abs(b["h"] - b["l"]) * 0.01) or 1e-9
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.35,
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
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=NY))
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


def _config_stop_target(state_root: Path) -> Tuple[float, float]:
    path = state_root / "strategy_instances.csv"
    stop_pts, target_pts = 50.0, 150.0
    if not path.exists():
        return stop_pts, target_pts
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return stop_pts, target_pts
    try:
        cfg = json.loads(rows[-1].get("config_json") or "{}")
        stop_pts = float(cfg.get("stop_pts") or stop_pts)
        target_pts = float(cfg.get("target_pts") or target_pts)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return stop_pts, target_pts


def _group_trades(fills: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, List[Dict[str, str]]] = {}
    for row in fills:
        tid = str(row.get("trade_id") or "").strip()
        if not tid:
            continue
        by_id.setdefault(tid, []).append(row)
    trades: List[Dict[str, Any]] = []
    for tid, rows in by_id.items():
        rows = sorted(rows, key=lambda r: r.get("ts") or "")
        entry = next(
            (r for r in rows if (r.get("reason") or "").strip() in ENTRY_REASONS
             and not str(r.get("reason") or "").startswith("runner_entry")),
            None,
        )
        if entry is None:
            entry = next((r for r in rows if (r.get("reason") or "").strip() in ENTRY_REASONS), rows[0])
        exits = [r for r in rows if (r.get("reason") or "").strip() in EXIT_REASONS]
        # Also treat any non-entry reduce as exit candidate when EXIT_REASONS miss.
        if not exits:
            exits = [r for r in rows if (r.get("reason") or "").strip() not in ENTRY_REASONS]
        side = "long" if (entry.get("side") or "").lower() == "buy" else "short"
        entry_qty = float(entry.get("quantity") or 0)
        exit_qty = sum(float(r.get("quantity") or 0) for r in exits)
        # Runner entries add size; completed when net flat-ish on primary+exits.
        runner_adds = sum(
            float(r.get("quantity") or 0)
            for r in rows
            if str(r.get("reason") or "").startswith("runner_entry")
            or (r.get("reason") or "") in {"add", "retest_add", "bb_add"}
        )
        open_qty_est = entry_qty + runner_adds - exit_qty
        completed = abs(open_qty_est) < 1e-9 and bool(exits)
        trades.append(
            {
                "trade_id": tid,
                "side": side,
                "entry": entry,
                "exits": exits,
                "fills": rows,
                "entry_ts": entry.get("ts") or "",
                "entry_price": float(entry.get("price") or 0),
                "completed": completed,
                "open_qty_est": open_qty_est,
            }
        )
    trades.sort(key=lambda t: t["entry_ts"])
    return trades


def _levels_for_trade(
    trade: Dict[str, Any],
    *,
    stop_pts: float,
    target_pts: float,
    orders: Sequence[Dict[str, str]],
) -> Tuple[Optional[float], Optional[float]]:
    entry_px = float(trade["entry_price"])
    side = trade["side"]
    if side == "long":
        stop, target = entry_px - stop_pts, entry_px + target_pts
    else:
        stop, target = entry_px + stop_pts, entry_px - target_pts

    tid = trade["trade_id"]
    for o in orders:
        if str(o.get("trade_id") or "") != tid:
            continue
        role = (o.get("bracket_role") or "").strip()
        px = o.get("stop_price") or o.get("limit_price")
        if px in (None, ""):
            continue
        try:
            px_f = float(px)
        except (TypeError, ValueError):
            continue
        if role in {"stop", "wide_stop", "runner_stop"}:
            stop = px_f
        elif role in {"target", "tp1", "tp2"}:
            # Prefer primary target (nearest / tp1) — keep first target-like.
            if role == "target" or abs(px_f - target) < abs(target - entry_px):
                target = px_f
    return stop, target


def _plot_trade_window(
    output_root: Path,
    instrument: str,
    trade: Dict[str, Any],
    *,
    out_path: Path,
    stop: Optional[float],
    target: Optional[float],
    end_ts: datetime,
    title_extra: str,
) -> Optional[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    state_root = Path(output_root) / "state"
    entry_ts = _parse_ny(trade["entry_ts"])
    start = entry_ts - timedelta(hours=2)
    end = end_ts + timedelta(minutes=30)
    bars = _load_bars_range(
        state_root / "bars" / ("%s_1m.csv" % instrument.upper()),
        start=start,
        end=end,
    )
    if len(bars) < 2:
        return None

    pf = _price_fmt(instrument)
    fig, ax = plt.subplots(figsize=(14, 7.0), dpi=130)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")

    # ~0.7 minute candle body
    _draw_candles(ax, bars, width=0.0005)

    if stop is not None:
        ax.axhline(stop, color="#e85d5d", lw=1.3, ls="-", alpha=0.95, label=("stop " + pf) % stop)
    if target is not None:
        ax.axhline(target, color="#3dcc91", lw=1.3, ls="-.", alpha=0.95, label=("target " + pf) % target)
    ax.axhline(
        float(trade["entry_price"]),
        color="#ffcc33",
        lw=1.0,
        ls=":",
        alpha=0.8,
        label=("entry " + pf) % float(trade["entry_price"]),
    )

    reason_colors = {
        "entry": "#ffcc33",
        "runner_entry": "#e0c35a",
        "add": "#e0c35a",
        "retest_add": "#e0c35a",
        "bb_add": "#e0c35a",
        "target": "#7ec8ff",
        "tp1": "#7ec8ff",
        "stop": "#ff8a7a",
        "runner_stop": "#ff8a7a",
    }
    for fill in trade["fills"]:
        ft = _parse_ny(fill["ts"])
        if ft < start or ft > end:
            continue
        price = float(fill["price"])
        side = (fill.get("side") or "").lower()
        reason = (fill.get("reason") or "").strip() or "fill"
        marker = "v" if side == "sell" else "^"
        color = reason_colors.get(reason, "#7ec8ff")
        if reason.startswith("runner_entry"):
            color = reason_colors["runner_entry"]
        ax.scatter(
            [ft],
            [price],
            marker=marker,
            s=120,
            color=color,
            edgecolors="#111",
            linewidths=0.7,
            zorder=6,
            label=("%s %s × %s @ " + pf) % (reason, side, fill.get("quantity"), price),
        )

    book = "oanda" if "oanda" in str(output_root).lower() else "paper"
    tid_short = _tid_short(str(trade["trade_id"]))
    _style_ax(
        ax,
        title="%s ST+PMC %s — %s %s %s"
        % (instrument.upper(), book, trade["side"], tid_short, title_extra),
    )
    ys = [b["l"] for b in bars] + [b["h"] for b in bars]
    for fill in trade["fills"]:
        ys.append(float(fill["price"]))
    if stop is not None:
        ys.append(stop)
    if target is not None:
        # Keep far runners from crushing the view — only include if near price.
        core_lo, core_hi = min(ys), max(ys)
        span = (core_hi - core_lo) or 1.0
        if (core_lo - span) <= target <= (core_hi + span):
            ys.append(target)
    span = (max(ys) - min(ys)) or 1.0
    ax.set_ylim(min(ys) - span * 0.1, max(ys) + span * 0.1)
    ax.set_xlim(bars[0]["dt"], bars[-1]["dt"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def write_completed_trade_chart(
    output_root: Path,
    instrument: str,
    trade: Dict[str, Any],
    *,
    stop_pts: float,
    target_pts: float,
    orders: Sequence[Dict[str, str]],
) -> Optional[Path]:
    if not trade.get("completed"):
        return None
    entry_ts = _parse_ny(trade["entry_ts"])
    last_exit = trade["exits"][-1]
    exit_ts = _parse_ny(last_exit["ts"])
    stop, target = _levels_for_trade(trade, stop_pts=stop_pts, target_pts=target_pts, orders=orders)
    tid_short = _tid_short(str(trade["trade_id"]))
    out = Path(output_root) / "charts" / (
        "%s_st_pmc_trade_%s_%s.png" % (instrument.lower(), tid_short, entry_ts.date().isoformat())
    )
    if out.exists():
        return out
    exit_reason = (last_exit.get("reason") or "exit").strip()
    return _plot_trade_window(
        output_root,
        instrument,
        trade,
        out_path=out,
        stop=stop,
        target=target,
        end_ts=exit_ts,
        title_extra="closed %s @ %s" % (exit_reason, _price_fmt(instrument) % float(last_exit["price"])),
    )


def write_open_trade_chart(
    output_root: Path,
    instrument: str,
    trade: Dict[str, Any],
    *,
    stop_pts: float,
    target_pts: float,
    orders: Sequence[Dict[str, str]],
    as_of: Optional[datetime] = None,
) -> Optional[Path]:
    entry_ts = _parse_ny(trade["entry_ts"])
    end_ts = as_of or datetime.now(tz=NY)
    stop, target = _levels_for_trade(trade, stop_pts=stop_pts, target_pts=target_pts, orders=orders)
    tid_short = _tid_short(str(trade["trade_id"]))
    out = Path(output_root) / "charts" / (
        "%s_st_pmc_open_%s_%s.png" % (instrument.lower(), tid_short, entry_ts.date().isoformat())
    )
    return _plot_trade_window(
        output_root,
        instrument,
        trade,
        out_path=out,
        stop=stop,
        target=target,
        end_ts=end_ts,
        title_extra="OPEN qty≈%.0f last %s"
        % (float(trade.get("open_qty_est") or 0), end_ts.astimezone(NY).strftime("%H:%M ET")),
    )


def update_st_pmc_charts(
    output_root: Path,
    instrument: str,
    *,
    refresh_open: bool = True,
) -> List[Path]:
    """Write missing completed-trade charts; optionally refresh open-trade overlays."""

    output_root = Path(output_root)
    state_root = output_root / "state"
    fills_path = state_root / "fills.csv"
    orders_path = state_root / "orders.csv"
    if not fills_path.exists():
        return []

    fills = list(csv.DictReader(fills_path.open(encoding="utf-8")))
    if not fills:
        return []
    orders = list(csv.DictReader(orders_path.open(encoding="utf-8"))) if orders_path.exists() else []
    stop_pts, target_pts = _config_stop_target(state_root)
    written: List[Path] = []

    for trade in _group_trades(fills):
        if trade.get("completed"):
            path = write_completed_trade_chart(
                output_root,
                instrument,
                trade,
                stop_pts=stop_pts,
                target_pts=target_pts,
                orders=orders,
            )
            if path is not None:
                written.append(path)
        elif refresh_open and abs(float(trade.get("open_qty_est") or 0)) > 1e-9:
            path = write_open_trade_chart(
                output_root,
                instrument,
                trade,
                stop_pts=stop_pts,
                target_pts=target_pts,
                orders=orders,
            )
            if path is not None:
                written.append(path)
    return written


def maybe_update_st_pmc_charts(
    output_root: Path,
    instrument: str,
    *,
    open_positions: int = 0,
    force_open: bool = False,
    last_open_chart_at: Optional[float] = None,
    now: Optional[float] = None,
    log: Optional[Any] = None,
) -> Tuple[List[Path], Optional[float]]:
    """Best-effort chart update for heartbeat loops.

    Returns ``(paths, new_last_open_chart_at)``. Open overlays refresh at most every
    ``OPEN_CHART_MIN_SECONDS`` unless ``force_open``.
    """
    import time as _time

    now = float(now if now is not None else _time.time())
    refresh_open = False
    new_last = last_open_chart_at
    if open_positions > 0 and (
        force_open
        or last_open_chart_at is None
        or (now - float(last_open_chart_at)) >= OPEN_CHART_MIN_SECONDS
    ):
        refresh_open = True
        new_last = now
    try:
        # Completed trades always; open overlays only when throttled gate opens.
        written = update_st_pmc_charts(
            output_root,
            instrument,
            refresh_open=refresh_open,
        )
        if log is not None and written:
            # Avoid spamming when only re-touching existing completed files.
            newish = [p for p in written if (now - p.stat().st_mtime) < 2.0]
            if newish:
                log(
                    output_root,
                    "ST+PMC chart wrote %d: %s" % (len(newish), ", ".join(p.name for p in newish)),
                )
        return written, new_last if refresh_open else last_open_chart_at
    except Exception as exc:
        if log is not None:
            log(
                output_root,
                "ST+PMC chart failed for %s: %s: %s" % (instrument, type(exc).__name__, exc),
            )
        return [], last_open_chart_at
