"""Overlay weekly_open_day_breakout fills onto existing weekly level charts.

Re-renders ISO-week PNGs under
``live/state/quarterly_atr4_top3_trade_charts/weekly_levels/<sym>/charts/``
for every week that has a broker entry fill, keeping open-day + ATR + weekly-open
levels and adding entry / stop / TP ladder guides + fill markers.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import load_4h, plot_candles, price_fmt, slug, week_bounds, wilder_atr, ATR_LEN, NY
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, ensure_4h_csv
from .quarterly_atr4_weekly_level_charts import (
    atr_at_end,
    draw_opening_day_range,
    draw_weekly_atr_bands,
    draw_weekly_open,
    opening_day_slice,
    shade_days,
)
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CHARTS = REPO / "live" / "state" / "quarterly_atr4_top3_trade_charts" / "weekly_levels"
DEFAULT_FILLS = (
    REPO
    / "live"
    / "state"
    / "weekly_open_day_breakout_1m_broker"
    / "states"
    / "gbpusd_weekly_open_day_breakout"
)

ROLE_COLORS = {
    "entry": "#1565c0",
    "stop": "#c62828",
    "tp1": "#2e7d32",
    "tp2": "#00838f",
    "tp3": "#ef6c00",
    "week_close": "#6d4c41",
    "breakout": "#f9a825",
    "swing": "#6a1b9a",
}
BULL_HIVOL_SHADE = "#9e9e9e"
SIGNAL_OFFSET = pd.Timedelta(hours=4)


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS_TRADES.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _parse_ts(raw: Any) -> pd.Timestamp:
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").tz_convert(NY)
    return ts.tz_convert(NY)


def _iso_week(ts: pd.Timestamp) -> Tuple[int, int]:
    iso = ts.isocalendar()
    if hasattr(iso, "year"):
        return int(iso.year), int(iso.week)
    return int(iso[0]), int(iso[1])


def _trade_pnl_by_id(state_root: Path) -> Dict[str, float]:
    """Sum unit_trades.net_usd by trade_id (includes fees)."""
    path = state_root / "unit_trades.csv"
    if not path.exists():
        return {}
    units = pd.read_csv(path)
    if units.empty or "trade_id" not in units.columns or "net_usd" not in units.columns:
        return {}
    return units.groupby(units["trade_id"].astype(str))["net_usd"].sum().astype(float).to_dict()


def _fmt_pnl(usd: float) -> str:
    return "PnL $%+.0f" % float(usd)


def _load_breakout_arms(state_root: Path) -> pd.DataFrame:
    path = state_root / "feature_snapshots.csv"
    if not path.exists():
        return pd.DataFrame()
    fs = pd.read_csv(path)
    if fs.empty or "feature_name" not in fs.columns:
        return pd.DataFrame()
    # Prefer detect (structural or gated record) over legacy arm-at-breakout.
    for name in ("wod_breakout_detect", "wod_breakout_arm"):
        arms = fs[fs["feature_name"].astype(str) == name].copy()
        if not arms.empty:
            break
    else:
        return pd.DataFrame()
    if arms.empty:
        return arms
    arms["event_ts"] = arms["event_ts"].map(_parse_ts)
    # Engine stamps completion (left+4h); chart candles use left edge.
    arms["bar_left"] = arms["event_ts"] - SIGNAL_OFFSET
    dirs: List[str] = []
    closes: List[float] = []
    for _, row in arms.iterrows():
        ref = str(row.get("value_ref") or "")
        direction = ""
        close_px = float("nan")
        if ":" in ref:
            direction, px = ref.split(":", 1)
            try:
                close_px = float(px)
            except ValueError:
                close_px = float("nan")
        meta_raw = row.get("metadata_json")
        if meta_raw and (not direction or not np.isfinite(close_px)):
            try:
                meta = json.loads(str(meta_raw))
                direction = str(meta.get("direction") or direction)
            except Exception:
                pass
        dirs.append(direction.lower())
        closes.append(close_px)
    arms["direction"] = dirs
    arms["breakout_close"] = closes
    return arms.reset_index(drop=True)


def _load_swing_arms(state_root: Path) -> pd.DataFrame:
    """Swing entry arms with swing_ts/close from feature metadata (preferred for charts)."""
    path = state_root / "feature_snapshots.csv"
    if not path.exists():
        return pd.DataFrame()
    fs = pd.read_csv(path)
    if fs.empty or "feature_name" not in fs.columns:
        return pd.DataFrame()
    arms = fs[fs["feature_name"].astype(str) == "wod_swing_entry_arm"].copy()
    if arms.empty:
        return arms
    arms["event_ts"] = arms["event_ts"].map(_parse_ts)
    rows = []
    for _, row in arms.iterrows():
        meta: Dict[str, Any] = {}
        try:
            meta = json.loads(str(row.get("metadata_json") or "{}"))
        except Exception:
            meta = {}
        direction = str(meta.get("direction") or "")
        ref = str(row.get("value_ref") or "")
        if not direction and ":" in ref:
            direction = ref.split(":", 1)[0]
        swing_ts = meta.get("swing_ts")
        swing_close = meta.get("swing_close")
        if swing_ts is None:
            continue
        st = _parse_ts(str(swing_ts))
        try:
            sc = float(swing_close) if swing_close is not None else float("nan")
        except (TypeError, ValueError):
            sc = float("nan")
        rows.append(
            {
                "arm_ts": row["event_ts"],
                "swing_left": st - SIGNAL_OFFSET,
                "swing_close": sc,
                "direction": direction.lower(),
            }
        )
    return pd.DataFrame(rows)


def _attach_swings(trades: List[dict], swing_arms: pd.DataFrame) -> None:
    if swing_arms.empty:
        for tr in trades:
            tr["swing_left"] = None
            tr["swing_close"] = None
        return
    for tr in trades:
        want = "long" if tr["direction"] == "Long" else "short"
        entry = tr["entry_ts"]
        cand = swing_arms[
            (swing_arms["direction"] == want) & (swing_arms["arm_ts"] <= entry + pd.Timedelta(minutes=5))
        ]
        if cand.empty:
            tr["swing_left"] = None
            tr["swing_close"] = None
            continue
        same_week = []
        for _, row in cand.iterrows():
            y, w = _iso_week(row["swing_left"])
            if y == tr["iso_year"] and w == tr["iso_week"]:
                same_week.append(row)
        pool = same_week if same_week else [r for _, r in cand.iterrows()]
        best = min(pool, key=lambda r: abs((r["arm_ts"] - entry).total_seconds()))
        tr["swing_left"] = best["swing_left"]
        tr["swing_close"] = float(best["swing_close"]) if np.isfinite(best["swing_close"]) else None


def _attach_breakouts(trades: List[dict], arms: pd.DataFrame) -> None:
    """Match each trade to its wod_breakout_arm (same direction, arm ≤ entry)."""
    if arms.empty:
        for tr in trades:
            tr["breakout_left"] = None
            tr["breakout_close"] = None
            tr["breakout_direction"] = ("long" if tr["direction"] == "Long" else "short")
        return
    for tr in trades:
        want = "long" if tr["direction"] == "Long" else "short"
        entry = tr["entry_ts"]
        cand = arms[(arms["direction"] == want) & (arms["event_ts"] <= entry + pd.Timedelta(minutes=5))]
        if cand.empty:
            cand = arms[arms["direction"] == want]
        if cand.empty:
            tr["breakout_left"] = None
            tr["breakout_close"] = None
            tr["breakout_direction"] = want
            continue
        # Prefer arm in the same ISO week, else nearest before entry.
        same_week = []
        for _, row in cand.iterrows():
            y, w = _iso_week(row["bar_left"])
            if y == tr["iso_year"] and w == tr["iso_week"]:
                same_week.append(row)
        pool = same_week if same_week else [r for _, r in cand.iterrows()]
        best = min(pool, key=lambda r: abs((r["event_ts"] - entry).total_seconds()))
        tr["breakout_left"] = best["bar_left"]
        tr["breakout_close"] = float(best["breakout_close"]) if np.isfinite(best["breakout_close"]) else None
        tr["breakout_direction"] = want


def _is_pullback_swing_bar(direction: str, open_: float, high: float, low: float, close: float) -> bool:
    span = float(high) - float(low)
    mid = 0.5 * (float(high) + float(low))
    if direction == "long":
        if float(close) < float(open_):
            return True
        return span > 0 and float(close) <= mid
    if direction == "short":
        if float(close) > float(open_):
            return True
        return span > 0 and float(close) >= mid
    return False


def _first_swing_after(
    bars: pd.DataFrame,
    breakout_left: pd.Timestamp,
    direction: str,
    *,
    require_pullback: bool = True,
) -> Optional[Tuple[pd.Timestamp, float]]:
    """First causal fractal swing after breakout; return (bar_left, close).

    Short → swing high close; long → swing low close.
    With ``require_pullback``, reject trend-continuation fractals (e.g. green
    bar whose wick alone is a lower low).
    """
    if bars.empty or breakout_left is None:
        return None
    idx = bars.index
    pos = idx.searchsorted(breakout_left, side="left")
    if pos >= len(idx) or abs((idx[pos] - breakout_left).total_seconds()) > 3600:
        if len(idx) == 0:
            return None
        pos = int(np.argmin([abs((t - breakout_left).total_seconds()) for t in idx]))
    opens = bars["open"].to_numpy(dtype=float) if "open" in bars.columns else bars["close"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    start = pos + 1
    for i in range(start, len(bars) - 1):
        is_fractal = False
        if direction == "short" and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            is_fractal = True
        elif direction == "long" and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            is_fractal = True
        if not is_fractal:
            continue
        if require_pullback and not _is_pullback_swing_bar(
            direction, float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i])
        ):
            continue
        return idx[i], float(closes[i])
    return None


def bull_hivol_active_mask(
    bars: pd.DataFrame,
    *,
    ma_len: int = 200,
    vol_ret_days: int = 20,
    vol_median_lookback: int = 252,
) -> pd.Series:
    """Causal bull×hivol gate at each 4h bar (matches plugin ``_regime_ok``)."""
    if bars.empty:
        return pd.Series(dtype=bool)
    active = []
    daily_closes: List[float] = []
    daily_day: Optional[str] = None
    daily_close: Optional[float] = None
    for ts, row in bars.iterrows():
        day = ts.tz_convert(NY).strftime("%Y-%m-%d") if ts.tzinfo else str(ts.date())
        px = float(row["close"])
        if daily_day and daily_day != day and daily_close is not None:
            daily_closes.append(float(daily_close))
            # keep history bounded
            keep = ma_len + vol_ret_days + vol_median_lookback + 50
            if len(daily_closes) > keep:
                daily_closes = daily_closes[-keep:]
        daily_day = day
        daily_close = px
        closes = list(daily_closes)
        if daily_close is not None:
            closes = closes + [float(daily_close)]
        ok = False
        if len(closes) >= ma_len:
            ma = sum(closes[-ma_len:]) / float(ma_len)
            if closes[-1] >= ma:
                rets: List[float] = []
                for i in range(1, len(closes)):
                    p0 = float(closes[i - 1])
                    p1 = float(closes[i])
                    if p0 > 0:
                        rets.append((p1 - p0) / p0)
                if len(rets) >= vol_ret_days:
                    vols: List[float] = []
                    for end_i in range(vol_ret_days - 1, len(rets)):
                        window = rets[end_i - vol_ret_days + 1 : end_i + 1]
                        mean = sum(window) / float(len(window))
                        var = sum((x - mean) ** 2 for x in window) / float(len(window))
                        vols.append(float(np.sqrt(var) * np.sqrt(252.0)))
                    if len(vols) >= 30:
                        cur = vols[-1]
                        hist = vols[:-1][-vol_median_lookback:]
                        if hist:
                            med = sorted(hist)[len(hist) // 2]
                            ok = cur >= med
        active.append(ok)
    return pd.Series(active, index=bars.index, dtype=bool)


def _shade_bull_hivol(ax, mask: pd.Series, w0: pd.Timestamp, w1: pd.Timestamp) -> None:
    if mask.empty:
        return
    sub = mask[(mask.index >= w0) & (mask.index < w1)]
    if sub.empty:
        return
    # Contiguous True spans using each bar's 4h width.
    in_run = False
    run_start = None
    labeled = False
    times = list(sub.index)
    vals = list(sub.astype(bool).values)
    for i, (ts, ok) in enumerate(zip(times, vals)):
        if ok and not in_run:
            in_run = True
            run_start = ts
        end_run = (not ok and in_run) or (ok and i == len(times) - 1 and in_run)
        if end_run:
            run_end = ts + SIGNAL_OFFSET if ok else ts
            ax.axvspan(
                run_start,
                min(run_end, w1),
                color=BULL_HIVOL_SHADE,
                alpha=0.28,
                zorder=0.5,
                label="bull×hivol" if not labeled else None,
            )
            labeled = True
            in_run = False
            run_start = None


def _mark_breakout_and_swing(
    ax,
    *,
    bars: pd.DataFrame,
    trades: Sequence[dict],
    labeled: set,
    extras: List[float],
    fmt: str,
    w0: pd.Timestamp,
    w1: pd.Timestamp,
) -> None:
    width_days = (4.0 / 24.0) * 0.72
    for tr in trades:
        left = tr.get("breakout_left")
        direction = str(tr.get("breakout_direction") or ("long" if tr["direction"] == "Long" else "short"))
        if left is None:
            continue
        # Snap to chart bar
        window = bars[(bars.index >= w0 - SIGNAL_OFFSET) & (bars.index < w1 + pd.Timedelta(days=3))]
        if window.empty:
            continue
        pos = window.index.searchsorted(left, side="left")
        if pos >= len(window):
            pos = len(window) - 1
        if abs((window.index[pos] - left).total_seconds()) > 2 * 3600 and pos > 0:
            # nearest
            pos = int(np.argmin([abs((t - left).total_seconds()) for t in window.index]))
        bts = window.index[pos]
        brow = window.iloc[pos]
        # Highlight breakout candle
        xi = mdates.date2num(bts.to_pydatetime())
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, float(brow["low"])),
                width_days,
                max(float(brow["high"]) - float(brow["low"]), 1e-6),
                facecolor="none",
                edgecolor=ROLE_COLORS["breakout"],
                linewidth=2.0,
                zorder=10,
                label="breakout" if "breakout" not in labeled else None,
            )
        )
        labeled.add("breakout")
        br_close = tr.get("breakout_close")
        if br_close is None or not np.isfinite(br_close):
            br_close = float(brow["close"])
        ax.scatter(
            [bts + pd.Timedelta(hours=2)],
            [br_close],
            marker="D",
            s=70,
            color=ROLE_COLORS["breakout"],
            edgecolors="white",
            linewidths=0.6,
            zorder=13,
        )
        extras.append(float(brow["high"]))
        extras.append(float(brow["low"]))

        # Prefer plugin swing arm metadata (respects swing_before_regime timing).
        swing_ts = tr.get("swing_left")
        swing_close = tr.get("swing_close")
        if swing_ts is None or swing_close is None or not np.isfinite(float(swing_close)):
            swing = _first_swing_after(window, bts, direction)
            if swing is None:
                continue
            swing_ts, swing_close = swing
        if swing_ts < w0 or swing_ts >= w1:
            continue
        label = "swing H close" if direction == "short" else "swing L close"
        ax.hlines(
            swing_close,
            max(swing_ts, w0),
            w1,
            colors=ROLE_COLORS["swing"],
            linestyles="--",
            linewidth=1.5,
            alpha=0.95,
            zorder=9,
            label=label if label not in labeled else None,
        )
        labeled.add(label)
        ax.scatter(
            [swing_ts + pd.Timedelta(hours=2)],
            [swing_close],
            marker="s",
            s=80,
            color=ROLE_COLORS["swing"],
            edgecolors="white",
            linewidths=0.6,
            zorder=13,
        )
        ax.text(
            min(swing_ts + pd.Timedelta(hours=4), w1 - pd.Timedelta(hours=1)),
            swing_close,
            (" %s " % label) + (fmt % swing_close),
            color=ROLE_COLORS["swing"],
            fontsize=7.5,
            va="bottom",
            ha="left",
            zorder=14,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 0.8},
        )
        extras.append(float(swing_close))


def _trade_windows(fills: pd.DataFrame, pnl_by_trade: Optional[Dict[str, float]] = None) -> List[dict]:
    out: List[dict] = []
    if fills.empty:
        return out
    pnl_by_trade = pnl_by_trade or {}
    fills = fills.copy()
    fills["ts_ny"] = fills["ts"].map(_parse_ts)
    for trade_id, g in fills.groupby("trade_id", sort=True):
        g = g.sort_values("ts_ny")
        entry = g[g["reason"] == "entry"]
        if entry.empty:
            continue
        e = entry.iloc[0]
        exits = g[g["reason"] != "entry"]
        exit_ts = exits["ts_ny"].iloc[-1] if not exits.empty else e["ts_ny"]
        y, w = _iso_week(e["ts_ny"])
        tid = str(trade_id)
        out.append(
            {
                "trade_id": tid,
                "direction": "Long" if str(e["side"]).lower() == "buy" else "Short",
                "entry_ts": e["ts_ny"],
                "entry_price": float(e["price"]),
                "exit_ts": exit_ts,
                "fills": g,
                "iso_year": y,
                "iso_week": w,
                "net_usd": float(pnl_by_trade.get(tid, 0.0)),
            }
        )
    return out


def _planned_levels(orders: pd.DataFrame, trade_id: str) -> Dict[str, float]:
    levels: Dict[str, float] = {}
    if orders.empty:
        return levels
    sub = orders[orders["trade_id"].astype(str) == str(trade_id)].copy()
    if sub.empty:
        return levels
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at")
    for _, row in sub.iterrows():
        role = str(row.get("bracket_role") or "")
        if role == "stop" and "stop" not in levels:
            px = row.get("stop_price")
            if pd.notna(px):
                levels["stop"] = float(px)
        elif role.startswith("tp") and role not in levels:
            px = row.get("limit_price")
            if pd.notna(px):
                levels[role] = float(px)
    return levels


def plot_week_with_trades(
    *,
    bars: pd.DataFrame,
    atr_series: pd.Series,
    w0: pd.Timestamp,
    w1: pd.Timestamp,
    iso_year: int,
    iso_week: int,
    out_path: Path,
    symbol: str,
    trades: Sequence[dict],
    orders: pd.DataFrame,
    regime_mask: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    fmt = price_fmt(symbol)
    window = bars[(bars.index >= w0) & (bars.index < w1)].copy()
    od = opening_day_slice(bars, w0, w1)
    atr_val = atr_at_end(atr_series, od)
    open_day = od.index[0].strftime("%Y-%m-%d") if not od.empty else ""

    fig, ax = plt.subplots(figsize=(16, 8.5))
    shade_days(ax, w0, w1)
    if regime_mask is not None:
        _shade_bull_hivol(ax, regime_mask, w0, w1)
    plot_candles(ax, window)
    hi, lo, mid = draw_opening_day_range(ax, od, w0, w1, fmt=fmt)
    weekly_open = draw_weekly_open(ax, window, w0, w1, fmt=fmt)
    extras: List[float] = []
    if mid is not None and atr_val is not None and atr_val > 0:
        extras.extend(draw_weekly_atr_bands(ax, mid, atr_val, w0, w1, fmt=fmt))
    if hi is not None:
        extras.extend([hi, lo])
    if weekly_open is not None:
        extras.append(weekly_open)

    labeled = set()
    _mark_breakout_and_swing(
        ax,
        bars=bars,
        trades=trades,
        labeled=labeled,
        extras=extras,
        fmt=fmt,
        w0=w0,
        w1=w1,
    )
    for tr in trades:
        entry_ts = tr["entry_ts"]
        exit_ts = min(tr["exit_ts"], w1 - pd.Timedelta(minutes=1))
        entry_px = float(tr["entry_price"])
        levels = _planned_levels(orders, tr["trade_id"])
        span_left = max(entry_ts, w0)
        span_right = max(span_left, exit_ts)
        ax.hlines(
            entry_px,
            span_left,
            span_right,
            colors=ROLE_COLORS["entry"],
            linestyles="-",
            linewidth=1.7,
            alpha=0.95,
            zorder=8,
            label="entry" if "entry" not in labeled else None,
        )
        labeled.add("entry")
        extras.append(entry_px)
        for role, px in levels.items():
            color = ROLE_COLORS.get(role, "#455a64")
            style = ":" if role == "stop" else "-."
            ax.hlines(
                px,
                span_left,
                span_right,
                colors=color,
                linestyles=style,
                linewidth=1.4,
                alpha=0.95,
                zorder=8,
                label=role if role not in labeled else None,
            )
            labeled.add(role)
            extras.append(px)
            ax.text(
                span_right,
                px,
                (" %s " % role) + (fmt % px),
                color=color,
                fontsize=7.5,
                va="center",
                ha="left",
                zorder=9,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 0.8},
            )
        marker = "^" if tr["direction"] == "Long" else "v"
        ax.scatter(
            [entry_ts],
            [entry_px],
            marker=marker,
            s=150,
            color=ROLE_COLORS["entry"],
            edgecolors="white",
            linewidths=0.8,
            zorder=11,
        )
        for _, fill in tr["fills"].iterrows():
            reason = str(fill["reason"])
            if reason == "entry":
                continue
            color = ROLE_COLORS.get(reason if reason.startswith("tp") else reason, "#455a64")
            if reason == "stop":
                color = ROLE_COLORS["stop"]
            ax.scatter(
                [fill["ts_ny"]],
                [float(fill["price"])],
                marker="o" if str(reason).startswith("tp") else "x",
                s=95 if str(reason).startswith("tp") else 120,
                color=color,
                linewidths=1.6,
                zorder=12,
                label=reason if reason not in labeled else None,
            )
            labeled.add(reason)
            extras.append(float(fill["price"]))

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is None or not np.isfinite(v):
                continue
            y_lo = min(y_lo, float(v))
            y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.06, 1e-4)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(w0, w1)
    atr_txt = (("ATR(14)@open-day=" + fmt) % atr_val) if atr_val is not None else "ATR n/a"
    week_pnl = sum(float(tr.get("net_usd") or 0.0) for tr in trades)
    if len(trades) == 1:
        pnl_txt = _fmt_pnl(week_pnl)
    else:
        parts = [_fmt_pnl(float(tr.get("net_usd") or 0.0)) for tr in trades]
        pnl_txt = "week %s (%s)" % (_fmt_pnl(week_pnl).replace("PnL ", ""), "; ".join(parts))
    ax.set_title(
        "%s 4h · %d-W%02d · open-day %s · %d trade(s) · %s · %s"
        % (symbol.upper(), iso_year, iso_week, open_day or "n/a", len(trades), pnl_txt, atr_txt)
    )
    ax.set_ylabel(symbol.upper())
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12], tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %m-%d %H:%M", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {
        "iso_year": iso_year,
        "iso_week": iso_week,
        "trades": len(trades),
        "net_usd": week_pnl,
        "chart": out_path.name,
    }


def run(
    *,
    market: str,
    charts_root: Path,
    state_root: Path,
    email: bool,
    bars_csv: Optional[Path] = None,
    no_regime_shade: bool = False,
) -> int:
    market = market.upper()
    if bars_csv is not None:
        csv_path = Path(bars_csv)
        if not csv_path.exists():
            raise SystemExit("Missing bars CSV at %s" % csv_path)
    else:
        if market not in MARKETS:
            raise SystemExit("Unknown market %s (pass --bars-csv for non-MARKETS tapes)" % market)
        csv_path = ensure_4h_csv(MARKETS[market])
    fills_path = state_root / "fills.csv"
    orders_path = state_root / "orders.csv"
    if not fills_path.exists():
        raise SystemExit("Missing fills at %s" % fills_path)

    market_charts = charts_root / slug(market) / "charts"
    market_charts.mkdir(parents=True, exist_ok=True)
    _progress(charts_root, "START overlay market=%s fills=%s → %s" % (market, fills_path, market_charts))

    fills = pd.read_csv(fills_path)
    orders = pd.read_csv(orders_path) if orders_path.exists() else pd.DataFrame()
    trades = _trade_windows(fills, pnl_by_trade=_trade_pnl_by_id(state_root))
    if not trades:
        _progress(charts_root, "No entry fills to overlay")
        return 1

    arms = _load_breakout_arms(state_root)
    _attach_breakouts(trades, arms)
    swing_arms = _load_swing_arms(state_root) if state_root is not None else pd.DataFrame()
    _attach_swings(trades, swing_arms)

    by_week: Dict[Tuple[int, int], List[dict]] = {}
    for tr in trades:
        by_week.setdefault((tr["iso_year"], tr["iso_week"]), []).append(tr)

    bars = load_4h(csv_path, market)
    atr_series = wilder_atr(bars, ATR_LEN)
    _progress(charts_root, "Computing bull×hivol regime mask …")
    regime_mask = None if no_regime_shade else bull_hivol_active_mask(bars)
    rows: List[dict] = []
    for (iso_year, iso_week), week_trades in sorted(by_week.items()):
        # Reconstruct week bounds from first entry (NY Monday).
        anchor = week_trades[0]["entry_ts"]
        w0, w1 = week_bounds(anchor)
        name = "%s_4h_%d_W%02d.png" % (slug(market), iso_year, iso_week)
        out_path = market_charts / name
        meta = plot_week_with_trades(
            bars=bars,
            atr_series=atr_series,
            w0=w0,
            w1=w1,
            iso_year=iso_year,
            iso_week=iso_week,
            out_path=out_path,
            symbol=market,
            trades=week_trades,
            orders=orders,
            regime_mask=regime_mask,
        )
        rows.append(meta)
        _progress(
            charts_root,
            "  wrote %s trades=%d" % (name, len(week_trades)),
        )

    pd.DataFrame(rows).to_csv(charts_root / slug(market) / "trade_overlay_manifest.csv", index=False)
    note = (
        "\n## Trade overlays\n\n"
        "Weeks with ``weekly_open_day_breakout`` fills re-rendered in place "
        "(%d weeks, %d campaigns). Reload PNGs to review.\n"
        % (len(rows), len(trades))
    )
    idx = charts_root / slug(market) / "INDEX.md"
    if idx.exists():
        text = idx.read_text(encoding="utf-8")
        if "Trade overlays" not in text:
            idx.write_text(text.rstrip() + "\n" + note, encoding="utf-8")
    body = (
        "Weekly open-day breakout trades overlaid on level charts\n\n"
        "Market: %s\nCharts: %s\nWeeks with trades: %d\nCampaigns: %d\n"
        "Fills: %s\n"
        % (market, market_charts, len(rows), len(trades), fills_path)
    )
    (charts_root / slug(market) / "EMAIL_TRADES.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: weekly breakout trades on level charts", body=body)
    try:
        hub_path = str(charts_root.resolve().relative_to(REPO.resolve()))
    except ValueError:
        hub_path = str(charts_root)
    log_run(
        run_class="other",
        variant_slug="weekly_open_day_breakout_chart_overlay",
        instrument=market,
        hub_path=hub_path,
        trades=len(trades),
        notes="%d weeks overlaid" % len(rows),
    )
    _progress(charts_root, "DONE weeks=%d trades=%d" % (len(rows), len(trades)))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--market", default="GBPUSD")
    p.add_argument("--charts-root", type=Path, default=DEFAULT_CHARTS)
    p.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_FILLS,
        help="Broker state with fills.csv / orders.csv",
    )
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--bars-csv",
        type=Path,
        default=None,
        help="Optional 4h OHLC CSV override (e.g. YM front-month tape matching fills)",
    )
    p.add_argument(
        "--no-regime-shade",
        action="store_true",
        help="Skip bull×hivol background shading (ungated books)",
    )
    args = p.parse_args(argv)
    return run(
        market=args.market,
        charts_root=args.charts_root,
        state_root=args.state_root,
        email=bool(args.email),
        bars_csv=args.bars_csv,
        no_regime_shade=bool(args.no_regime_shade),
    )


if __name__ == "__main__":
    raise SystemExit(main())
