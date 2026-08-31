#!/usr/bin/env python3
"""Causal CHOP/efficiency range-breakout detector for NQ and YM bars.

The daily detector follows the fixed 20-day specification from the research
notes. Intraday runs use the same calculation on completed 20-bar windows:

- completed candles only
- CHOP(20) for path choppiness
- 20-bar directional efficiency for net displacement
- 20-bar range width divided by ATR(20), ranked against prior 252 values only
- two completed-bar confirmation

Each contiguous confirmed range segment is frozen at its last completed bar.
The first later bar close outside that frozen 20-bar box is recorded as a
breakout. Each breakout gets its own one-year forward chart, even when another
range appears inside that same forward window.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "live" / "state" / "chop_20d_range_breakouts_nq_ym"
DEFAULT_SOURCES = {
    "D": {
        "NQ": ROOT / "nq" / "nq_daily.csv",
        "YM": ROOT / "ym" / "ym_daily.csv",
    },
    "4h": {
        "NQ": ROOT / "live" / "state" / "_cache" / "bars_4h" / "nq_4h.csv",
        "YM": ROOT / "live" / "state" / "_cache" / "bars_4h" / "ym_4h.csv",
    },
    "1h": {
        "NQ": ROOT / "live" / "state" / "trend_momentum_sweep" / "states" / "nq_1h" / "bars" / "NQ_1h.csv",
        "YM": ROOT / "live" / "state" / "trend_momentum_sweep" / "states" / "ym_1h" / "bars" / "YM_1h.csv",
    },
}

RANGE_LIKE_STATES = {"RANGING", "COMPRESSED_RANGE"}


@dataclass(frozen=True)
class DetectorParams:
    range_lookback: int = 20
    atr_lookback: int = 20
    baseline_lookback: int = 252
    chop_range_threshold: float = 61.8
    chop_trend_threshold: float = 38.2
    efficiency_range_max: float = 0.35
    efficiency_trend_min: float = 0.55
    width_pctl_low: float = 0.20
    width_pctl_high: float = 0.80
    confirm_days: int = 2
    min_history: int = 252
    max_wait_bars: int = 252


@dataclass
class RangeSegment:
    market: str
    timeframe: str
    segment_id: int
    start_idx: int
    end_idx: int
    start_ts: str
    end_ts: str
    range_high: float
    range_low: float
    range_width: float
    chop_20: float
    efficiency_20: float
    range_atr_20: float
    range_atr_percentile_252: float
    confirmed_regime: str
    raw_regime: str


@dataclass
class BreakoutEvent:
    market: str
    timeframe: str
    event_id: int
    segment_id: int
    range_start_ts: str
    range_end_ts: str
    range_bars: int
    breakout_ts: str
    direction: str
    range_high: float
    range_low: float
    range_width: float
    breakout_close: float
    breakout_gap_pts: float
    bars_waited: int
    effective_trade_ts: str
    chop_20: float
    efficiency_20: float
    range_atr_20: float
    range_atr_percentile_252: float
    forward_close_5bar: float
    forward_close_10bar: float
    forward_close_20bar: float
    forward_close_60bar: float
    forward_close_252bar: float
    forward_mfe_252bar_pts: float
    forward_mae_252bar_pts: float
    chart: str


def _fmt_money_like(x: float, digits: int = 2) -> str:
    if not np.isfinite(x):
        return "NA"
    return f"{x:,.{digits}f}"


def _pct(x: float) -> str:
    if not np.isfinite(x):
        return "NA"
    return f"{100.0 * x:.1f}%"


def _canonical_timeframe(timeframe: str) -> str:
    tf = str(timeframe).strip().lower()
    if tf in {"d", "1d", "daily", "day"}:
        return "D"
    if tf in {"4h", "4hr", "4hour", "4-hour"}:
        return "4h"
    if tf in {"1h", "h", "hourly", "hour", "1hr"}:
        return "1h"
    raise ValueError(f"unsupported timeframe {timeframe!r}; use D, 4h, or 1h")


def _bar_ts(value, timeframe: str) -> pd.Timestamp:
    if timeframe == "D":
        return pd.Timestamp(value).tz_localize(None).normalize()
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("America/New_York")


def _ts_str(value, timeframe: str) -> str:
    ts = pd.Timestamp(value)
    if timeframe == "D":
        return ts.tz_localize(None).date().isoformat()
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC").tz_convert("America/New_York")
    return ts.isoformat()


def _slug_ts(value, timeframe: str) -> str:
    s = _ts_str(value, timeframe)
    return s.replace(":", "").replace("+", "p").replace("-", "").replace("T", "_")


def _bar_width_days(timeframe: str) -> float:
    if timeframe == "D":
        return 0.68
    if timeframe == "4h":
        return (4.0 / 24.0) * 0.68
    return (1.0 / 24.0) * 0.72


def _bar_label(timeframe: str) -> str:
    return "trading days" if timeframe == "D" else f"{timeframe} bars"


def _forward_horizon_suffix(timeframe: str) -> str:
    return "d" if timeframe == "D" else "bar"


def load_bars(path: Path, timeframe: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    ts_col = "date" if "date" in df.columns else "ts" if "ts" in df.columns else "ts_event" if "ts_event" in df.columns else ""
    if not ts_col:
        raise ValueError(f"{path} is missing a date/ts/ts_event column")
    required = {"open", "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")
    if timeframe == "D":
        df["date"] = pd.to_datetime(df[ts_col]).dt.tz_localize(None).dt.normalize()
    else:
        df["date"] = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert("America/New_York")
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    else:
        df["volume"] = 0
    if "symbol" not in df.columns:
        df["symbol"] = ""
    df = df.dropna(subset=["date", "open", "high", "low", "close"])
    df = df.sort_values("date").drop_duplicates("date", keep="last")
    return df.reset_index(drop=True)


def add_range_metrics(daily: pd.DataFrame, params: DetectorParams) -> pd.DataFrame:
    d = daily.copy()
    high = d["high"].astype(float)
    low = d["low"].astype(float)
    close = d["close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    d["true_range"] = tr
    d["atr_20"] = tr.rolling(params.atr_lookback, min_periods=params.atr_lookback).mean()

    d["range_high_20"] = high.rolling(params.range_lookback, min_periods=params.range_lookback).max()
    d["range_low_20"] = low.rolling(params.range_lookback, min_periods=params.range_lookback).min()
    d["range_20"] = d["range_high_20"] - d["range_low_20"]
    sum_tr = tr.rolling(params.range_lookback, min_periods=params.range_lookback).sum()
    denom = d["range_20"].replace(0, np.nan)
    d["chop_20"] = 100.0 * np.log10(sum_tr / denom) / math.log10(params.range_lookback)

    path = close.diff().abs().rolling(params.range_lookback - 1, min_periods=params.range_lookback - 1).sum()
    net = (close - close.shift(params.range_lookback - 1)).abs()
    d["efficiency_20"] = net / path.replace(0, np.nan)
    d["range_atr_20"] = d["range_20"] / d["atr_20"].replace(0, np.nan)

    widths = d["range_atr_20"].to_numpy(dtype=float)
    width_pct = np.full(len(d), np.nan)
    for i, value in enumerate(widths):
        if i < params.min_history or not np.isfinite(value):
            continue
        prior = widths[max(0, i - params.baseline_lookback) : i]
        prior = prior[np.isfinite(prior)]
        if len(prior) == 0:
            continue
        width_pct[i] = float(np.mean(prior <= value))
    d["range_atr_percentile_252"] = width_pct

    raw = []
    for i, row in d.iterrows():
        if i < params.min_history:
            raw.append("UNKNOWN")
            continue
        chop = float(row["chop_20"])
        er = float(row["efficiency_20"])
        width_pct_i = float(row["range_atr_percentile_252"])
        width = float(row["range_atr_20"])
        if not all(np.isfinite(x) for x in (chop, er, width_pct_i, width)):
            raw.append("UNKNOWN")
        elif chop <= params.chop_trend_threshold and er >= params.efficiency_trend_min:
            raw.append("TRENDING")
        elif (
            chop >= params.chop_range_threshold
            and er <= params.efficiency_range_max
            and width_pct_i <= params.width_pctl_low
        ):
            raw.append("COMPRESSED_RANGE")
        elif (
            chop >= params.chop_range_threshold
            and er <= params.efficiency_range_max
            and width_pct_i <= params.width_pctl_high
        ):
            raw.append("RANGING")
        elif chop >= params.chop_range_threshold and width_pct_i > params.width_pctl_high:
            raw.append("VOLATILE_DISORDER")
        else:
            raw.append("TRANSITION")
    d["raw_regime"] = raw

    confirmed = []
    for i, state in enumerate(raw):
        if state == "UNKNOWN":
            confirmed.append("UNKNOWN")
            continue
        if i - params.confirm_days + 1 < 0:
            confirmed.append("TRANSITION")
            continue
        lookback_states = raw[i - params.confirm_days + 1 : i + 1]
        confirmed.append(state if all(s == state for s in lookback_states) else "TRANSITION")
    d["confirmed_regime"] = confirmed
    d["is_range_like"] = d["confirmed_regime"].isin(RANGE_LIKE_STATES)
    return d


def range_segments(market: str, timeframe: str, d: pd.DataFrame) -> List[RangeSegment]:
    segments: List[RangeSegment] = []
    active_start: Optional[int] = None
    segment_id = 0

    def close_segment(end_idx: int) -> None:
        nonlocal segment_id
        if active_start is None:
            return
        row = d.iloc[end_idx]
        segment_id += 1
        segments.append(
            RangeSegment(
                market=market,
                timeframe=timeframe,
                segment_id=segment_id,
                start_idx=int(active_start),
                end_idx=int(end_idx),
                start_ts=_ts_str(d.iloc[active_start]["date"], timeframe),
                end_ts=_ts_str(row["date"], timeframe),
                range_high=float(row["range_high_20"]),
                range_low=float(row["range_low_20"]),
                range_width=float(row["range_20"]),
                chop_20=float(row["chop_20"]),
                efficiency_20=float(row["efficiency_20"]),
                range_atr_20=float(row["range_atr_20"]),
                range_atr_percentile_252=float(row["range_atr_percentile_252"]),
                confirmed_regime=str(row["confirmed_regime"]),
                raw_regime=str(row["raw_regime"]),
            )
        )

    for i, row in d.iterrows():
        if bool(row["is_range_like"]):
            if active_start is None:
                active_start = int(i)
        elif active_start is not None:
            close_segment(int(i) - 1)
            active_start = None
    if active_start is not None:
        close_segment(len(d) - 1)
    return segments


def _forward_close(d: pd.DataFrame, idx: int, horizon: int) -> float:
    j = min(idx + horizon, len(d) - 1)
    if j <= idx:
        return np.nan
    return float(d.iloc[j]["close"] - d.iloc[idx]["close"])


def _forward_mfe_mae(d: pd.DataFrame, idx: int, direction: str, horizon: int = 252) -> Tuple[float, float]:
    end = min(idx + horizon, len(d) - 1)
    if end <= idx:
        return np.nan, np.nan
    window = d.iloc[idx + 1 : end + 1]
    entry = float(d.iloc[idx]["close"])
    if direction == "up":
        mfe = float(window["high"].max() - entry)
        mae = float(window["low"].min() - entry)
    else:
        mfe = float(entry - window["low"].min())
        mae = float(entry - window["high"].max())
    return mfe, mae


def detect_breakouts(
    market: str,
    timeframe: str,
    d: pd.DataFrame,
    segments: Iterable[RangeSegment],
    params: DetectorParams,
) -> Tuple[List[BreakoutEvent], List[dict]]:
    events: List[BreakoutEvent] = []
    expired: List[dict] = []
    event_id = 0
    for seg in segments:
        start = seg.end_idx + 1
        end = min(len(d), start + params.max_wait_bars)
        found_idx: Optional[int] = None
        direction = ""
        for i in range(start, end):
            c = float(d.iloc[i]["close"])
            if c > seg.range_high:
                found_idx = i
                direction = "up"
                break
            if c < seg.range_low:
                found_idx = i
                direction = "down"
                break
        if found_idx is None:
            expired.append(
                {
                    "market": market,
                    "timeframe": timeframe,
                    "segment_id": seg.segment_id,
                    "range_start_ts": seg.start_ts,
                    "range_end_ts": seg.end_ts,
                    "range_high": seg.range_high,
                    "range_low": seg.range_low,
                    "max_wait_bars": params.max_wait_bars,
                }
            )
            continue

        row = d.iloc[found_idx]
        breakout_close = float(row["close"])
        if direction == "up":
            breakout_gap = breakout_close - seg.range_high
        else:
            breakout_gap = seg.range_low - breakout_close
        next_idx = min(found_idx + 1, len(d) - 1)
        mfe, mae = _forward_mfe_mae(d, found_idx, direction)
        event_id += 1
        events.append(
            BreakoutEvent(
                market=market,
                timeframe=timeframe,
                event_id=event_id,
                segment_id=seg.segment_id,
                range_start_ts=seg.start_ts,
                range_end_ts=seg.end_ts,
                range_bars=int(seg.end_idx - seg.start_idx + 1),
                breakout_ts=_ts_str(row["date"], timeframe),
                direction=direction,
                range_high=seg.range_high,
                range_low=seg.range_low,
                range_width=seg.range_width,
                breakout_close=breakout_close,
                breakout_gap_pts=float(breakout_gap),
                bars_waited=int(found_idx - seg.end_idx),
                effective_trade_ts=_ts_str(d.iloc[next_idx]["date"], timeframe),
                chop_20=seg.chop_20,
                efficiency_20=seg.efficiency_20,
                range_atr_20=seg.range_atr_20,
                range_atr_percentile_252=seg.range_atr_percentile_252,
                forward_close_5bar=_forward_close(d, found_idx, 5),
                forward_close_10bar=_forward_close(d, found_idx, 10),
                forward_close_20bar=_forward_close(d, found_idx, 20),
                forward_close_60bar=_forward_close(d, found_idx, 60),
                forward_close_252bar=_forward_close(d, found_idx, 252),
                forward_mfe_252bar_pts=mfe,
                forward_mae_252bar_pts=mae,
                chart="",
            )
        )
    return events, expired


def plot_candles(ax: plt.Axes, bars: pd.DataFrame, width_days: float) -> None:
    xs = mdates.date2num(pd.to_datetime(bars["date"]).dt.to_pydatetime())
    up = bars["close"].to_numpy(dtype=float) >= bars["open"].to_numpy(dtype=float)
    colors = np.where(up, "#16815f", "#c43d4b")
    ax.vlines(xs, bars["low"], bars["high"], color=colors, linewidth=0.75, alpha=0.95, zorder=3)
    for x, o, c, color in zip(xs, bars["open"], bars["close"], colors):
        lower = min(float(o), float(c))
        height = abs(float(c) - float(o))
        if height == 0:
            height = max((float(bars["high"].max()) - float(bars["low"].min())) * 0.001, 0.01)
        rect = mpatches.Rectangle(
            (x - width_days / 2.0, lower),
            width_days,
            height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.45,
            alpha=0.85,
            zorder=4,
        )
        ax.add_patch(rect)


def _event_window(d: pd.DataFrame, seg: RangeSegment, event: BreakoutEvent) -> pd.DataFrame:
    breakout = pd.Timestamp(event.breakout_ts)
    start_idx = max(0, seg.start_idx - 20)
    start_date = d.iloc[start_idx]["date"]
    end_date = breakout + pd.DateOffset(years=1)
    return d[(d["date"] >= start_date) & (d["date"] <= end_date)].copy()


def plot_breakout_chart(
    market: str,
    timeframe: str,
    d: pd.DataFrame,
    seg: RangeSegment,
    event: BreakoutEvent,
    out_path: Path,
) -> None:
    plot = _event_window(d, seg, event)
    if plot.empty:
        return
    dates = pd.to_datetime(plot["date"])
    x = mdates.date2num(dates.dt.to_pydatetime())
    range_start = pd.Timestamp(event.range_start_ts)
    range_end = pd.Timestamp(event.range_end_ts)
    breakout = pd.Timestamp(event.breakout_ts)
    chart_end = dates.max()
    truncated = chart_end < breakout + pd.DateOffset(years=1)

    fig, (ax, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(18, 10.5),
        gridspec_kw={"height_ratios": [4.6, 1.35, 1.15], "hspace": 0.08},
        sharex=True,
    )
    fig.patch.set_facecolor("#f7f8fa")
    for a in (ax, ax2, ax3):
        a.set_facecolor("#fbfcfd")
        a.grid(True, alpha=0.25, linewidth=0.6)

    plot_candles(ax, plot, width_days=_bar_width_days(timeframe))
    ax.axhspan(event.range_low, event.range_high, color="#2563eb", alpha=0.065, zorder=0)
    ax.axhline(event.range_high, color="#1d4ed8", linewidth=1.25, linestyle="-", label="Frozen 20-bar range high")
    ax.axhline(event.range_low, color="#1d4ed8", linewidth=1.25, linestyle="-", label="Frozen 20-bar range low")
    ax.axvspan(range_start, range_end, color="#f59e0b", alpha=0.11, label="Confirmed range segment")
    ax.axvline(breakout, color="#111827", linewidth=1.2, linestyle="--", label="Breakout close")
    marker = "^" if event.direction == "up" else "v"
    marker_color = "#047857" if event.direction == "up" else "#b91c1c"
    ax.scatter(
        [breakout],
        [event.breakout_close],
        marker=marker,
        s=95,
        color=marker_color,
        edgecolor="#111827",
        linewidth=0.5,
        zorder=8,
        label=f"{event.direction.upper()} breakout",
    )
    ax.text(
        breakout,
        event.breakout_close,
        f" {event.direction.upper()} close {event.breakout_close:.2f}",
        va="bottom" if event.direction == "up" else "top",
        ha="left",
        fontsize=8.8,
        color="#111827",
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "#ffffff", "edgecolor": "#d1d5db", "alpha": 0.88},
        zorder=9,
    )

    y_min = float(min(plot["low"].min(), event.range_low))
    y_max = float(max(plot["high"].max(), event.range_high))
    pad = (y_max - y_min) * 0.06 if y_max > y_min else 1.0
    ax.set_ylim(y_min - pad, y_max + pad)
    title = (
        f"{market} CHOP20 range breakout {event.event_id:03d} | "
        f"{timeframe} | {event.direction.upper()} | range {event.range_start_ts} to {event.range_end_ts} | "
        f"breakout {event.breakout_ts}"
    )
    if truncated:
        title += " | forward window truncated by data end"
    ax.set_title(title, fontsize=12.5, fontweight="bold", loc="left")
    ax.set_ylabel(f"{timeframe} price")
    ax.legend(loc="upper left", fontsize=8, ncol=4, frameon=True)

    ax2.plot(plot["date"], plot["chop_20"], color="#7c3aed", linewidth=1.2, label="CHOP(20)")
    ax2.axhline(61.8, color="#7c3aed", linestyle="--", linewidth=0.8, alpha=0.75)
    ax2_t = ax2.twinx()
    ax2_t.plot(plot["date"], plot["efficiency_20"], color="#0891b2", linewidth=1.05, label="Efficiency(20)")
    ax2_t.axhline(0.35, color="#0891b2", linestyle="--", linewidth=0.8, alpha=0.75)
    ax2.set_ylabel("CHOP")
    ax2_t.set_ylabel("Efficiency")
    ax2.set_ylim(0, 100)
    ax2_t.set_ylim(0, 1)
    lines, labels = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_t.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc="upper left", fontsize=8, ncol=2)

    ax3.plot(plot["date"], plot["range_atr_percentile_252"], color="#374151", linewidth=1.1, label="Range/ATR prior-252 pct")
    ax3.axhspan(0.20, 0.80, color="#10b981", alpha=0.08, label="ordinary width band")
    ax3.axhline(0.20, color="#6b7280", linestyle="--", linewidth=0.8)
    ax3.axhline(0.80, color="#6b7280", linestyle="--", linewidth=0.8)
    ax3.set_ylim(-0.02, 1.02)
    ax3.set_ylabel("Width pct")
    ax3.legend(loc="upper left", fontsize=8)

    if timeframe == "D":
        ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    else:
        locator = mdates.AutoDateLocator(minticks=8, maxticks=14)
        ax3.xaxis.set_major_locator(locator)
        ax3.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    for label in ax3.get_xticklabels():
        label.set_rotation(45)
        label.set_ha("right")
    ax.set_xlim(x[0] - 2, x[-1] + 2)
    fig.subplots_adjust(left=0.055, right=0.945, top=0.93, bottom=0.12, hspace=0.08)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def write_csv(path: Path, rows: Iterable[dict], columns: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows), columns=columns).to_csv(path, index=False)


def summarize_market(
    market: str,
    timeframe: str,
    d: pd.DataFrame,
    events: List[BreakoutEvent],
    segments: List[RangeSegment],
    charts_written: int,
) -> dict:
    counts = d["confirmed_regime"].value_counts(dropna=False).to_dict()
    ev = pd.DataFrame([asdict(e) for e in events])
    direction_counts = ev["direction"].value_counts().to_dict() if not ev.empty else {}
    return {
        "market": market,
        "timeframe": timeframe,
        "start": _ts_str(d["date"].min(), timeframe),
        "end": _ts_str(d["date"].max(), timeframe),
        "total_bars": int(len(d)),
        "confirmed_range_bars": int(d["is_range_like"].sum()),
        "range_segments": int(len(segments)),
        "breakouts": int(len(events)),
        "charts_written": int(charts_written),
        "expired_segments": int(len(segments) - len(events)),
        "up_breakouts": int(direction_counts.get("up", 0)),
        "down_breakouts": int(direction_counts.get("down", 0)),
        "median_range_bars": float(np.median([s.end_idx - s.start_idx + 1 for s in segments])) if segments else np.nan,
        "median_wait_bars": float(np.median([e.bars_waited for e in events])) if events else np.nan,
        "avg_forward_20bar_pts": float(ev["forward_close_20bar"].mean()) if not ev.empty else np.nan,
        "avg_forward_60bar_pts": float(ev["forward_close_60bar"].mean()) if not ev.empty else np.nan,
        "avg_forward_252bar_pts": float(ev["forward_close_252bar"].mean()) if not ev.empty else np.nan,
        "state_counts": counts,
    }


def write_market_index(market_dir: Path, market: str, timeframe: str, summary: dict, events: List[BreakoutEvent]) -> None:
    label = _bar_label(timeframe)
    suffix = _forward_horizon_suffix(timeframe)
    lines = [
        f"# {market} {timeframe} CHOP20 Range Breakouts",
        "",
        "Causal detector using completed candles only. Each contiguous confirmed range segment freezes its final 20-bar high/low after the segment's final close. The first later candle close outside that frozen box is the breakout.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Timeframe | {timeframe} |",
        f"| Coverage | {summary['start']} to {summary['end']} |",
        f"| Bars | {summary['total_bars']:,} |",
        f"| Confirmed range-like bars | {summary['confirmed_range_bars']:,} |",
        f"| Range segments | {summary['range_segments']:,} |",
        f"| Breakouts detected | {summary['breakouts']:,} |",
        f"| Charts written | {summary['charts_written']:,} |",
        f"| Expired/no-break segments | {summary['expired_segments']:,} |",
        f"| Up / down breakouts | {summary['up_breakouts']:,} / {summary['down_breakouts']:,} |",
        f"| Median range length | {_fmt_money_like(summary['median_range_bars'], 1)} {label} |",
        f"| Median wait to breakout | {_fmt_money_like(summary['median_wait_bars'], 1)} {label} |",
        f"| Avg forward 20{suffix} close change | {_fmt_money_like(summary['avg_forward_20bar_pts'], 2)} pts |",
        f"| Avg forward 60{suffix} close change | {_fmt_money_like(summary['avg_forward_60bar_pts'], 2)} pts |",
        f"| Avg forward 252{suffix} close change | {_fmt_money_like(summary['avg_forward_252bar_pts'], 2)} pts |",
        "",
        "## Files",
        "",
        "- [bar_regimes.csv](bar_regimes.csv)",
        "- [range_segments.csv](range_segments.csv)",
        "- [range_breakouts.csv](range_breakouts.csv)",
        "- [expired_ranges.csv](expired_ranges.csv)",
        "- [charts/](charts/)",
        "",
        "## Breakout Charts",
        "",
        "| # | Breakout | Dir | Range End | Wait | Chart |",
        "|---:|---|---|---|---:|---|",
    ]
    for e in events:
        chart = Path(e.chart).name
        lines.append(
            f"| {e.event_id} | {e.breakout_ts} | {e.direction} | {e.range_end_ts} | {e.bars_waited} | [chart](charts/{chart}) |"
        )
    (market_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_root_summary(out_dir: Path, params: DetectorParams, summaries: List[dict]) -> None:
    lines = [
        "# CHOP20 Range Breakout Study - NQ / YM",
        "",
        "Causal range detector based on CHOP(20), directional efficiency, and 20-bar range width normalized by ATR(20). This is a detection/chart pack, not a broker replay or promoted trading system.",
        "",
        "## Detector",
        "",
        "| Parameter | Value |",
        "|---|---:|",
    ]
    for k, v in asdict(params).items():
        lines.append(f"| `{k}` | {v} |")
    lines.extend(
        [
            "",
            "## Causality",
            "",
            "- All regime features are calculated from completed candles.",
            "- Range width percentile compares the current value only to prior completed values.",
            "- A range segment is known after its final completed candle close.",
            "- Breakout detection uses the first later completed candle close outside the frozen box.",
            "- Charts intentionally run one year forward from each breakout and do not stop when a later range appears.",
            "",
            "## Markets",
            "",
            "| Timeframe | Market | Coverage | Bars | Range segments | Breakouts | Charts | Up / Down | Median wait | Index |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for s in summaries:
        lines.append(
            "| {timeframe} | {market} | {start} to {end} | {total_bars:,} | {range_segments:,} | {breakouts:,} | {charts_written:,} | {up_breakouts:,}/{down_breakouts:,} | {median_wait_bars:.1f} | [{market}](./{tf_slug}/{slug}/INDEX.md) |".format(
                tf_slug=s["timeframe"].lower(),
                slug=s["market"].lower(),
                **s,
            )
        )
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `summary.csv`",
            "- `{timeframe}/{market}/bar_regimes.csv`",
            "- `{timeframe}/{market}/range_segments.csv`",
            "- `{timeframe}/{market}/range_breakouts.csv`",
            "- `{timeframe}/{market}/charts/*.png`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_market(
    market: str,
    timeframe: str,
    path: Path,
    out_dir: Path,
    params: DetectorParams,
    max_charts: int = 0,
) -> dict:
    market = market.upper()
    timeframe = _canonical_timeframe(timeframe)
    market_dir = out_dir / timeframe.lower() / market.lower()
    chart_dir = market_dir / "charts"
    market_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    bars = load_bars(path, timeframe)
    regimes = add_range_metrics(bars, params)
    segments = range_segments(market, timeframe, regimes)
    events, expired = detect_breakouts(market, timeframe, regimes, segments, params)

    seg_by_id = {s.segment_id: s for s in segments}
    events_to_plot = events if max_charts <= 0 else events[:max_charts]
    for e in events_to_plot:
        fname = (
            f"{e.event_id:03d}_{_slug_ts(e.breakout_ts, timeframe)}_{e.direction}_"
            f"range_{_slug_ts(e.range_start_ts, timeframe)}_to_{_slug_ts(e.range_end_ts, timeframe)}.png"
        )
        rel = Path("charts") / fname
        e.chart = str(rel)
        plot_breakout_chart(market, timeframe, regimes, seg_by_id[e.segment_id], e, market_dir / rel)
    if max_charts > 0 and len(events) > max_charts:
        for e in events[max_charts:]:
            e.chart = ""

    regimes.to_csv(market_dir / "bar_regimes.csv", index=False)
    if timeframe == "D":
        regimes.to_csv(market_dir / "daily_regimes.csv", index=False)
    write_csv(market_dir / "range_segments.csv", (asdict(s) for s in segments), [f.name for f in fields(RangeSegment)])
    write_csv(market_dir / "range_breakouts.csv", (asdict(e) for e in events), [f.name for f in fields(BreakoutEvent)])
    write_csv(
        market_dir / "expired_ranges.csv",
        expired,
        [
            "market",
            "timeframe",
            "segment_id",
            "range_start_ts",
            "range_end_ts",
            "range_high",
            "range_low",
            "max_wait_bars",
        ],
    )

    summary = summarize_market(market, timeframe, regimes, events, segments, len(events_to_plot))
    write_market_index(market_dir, market, timeframe, summary, events_to_plot)
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--markets", nargs="+", default=["NQ", "YM"], help="Markets to run: NQ YM")
    p.add_argument("--timeframes", nargs="+", default=["D"], help="Timeframes to run: D 4h 1h")
    p.add_argument("--max-charts", type=int, default=0, help="Debug limit; 0 charts every breakout")
    p.add_argument("--max-wait", type=int, default=252, help="Max bars after a range segment to wait for breakout")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    params = DetectorParams(max_wait_bars=int(args.max_wait))
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "detector_params.json").write_text(json.dumps(asdict(params), indent=2) + "\n", encoding="utf-8")

    summaries = []
    for timeframe in args.timeframes:
        tf = _canonical_timeframe(timeframe)
        if tf not in DEFAULT_SOURCES:
            raise ValueError(f"unsupported timeframe {timeframe}; use one of {sorted(DEFAULT_SOURCES)}")
        for market in args.markets:
            m = market.upper()
            if m not in DEFAULT_SOURCES[tf]:
                raise ValueError(f"unsupported market {market}; use one of {sorted(DEFAULT_SOURCES[tf])}")
            source = DEFAULT_SOURCES[tf][m]
            print(f"RUN {m} {tf} from {source}")
            summaries.append(process_market(m, tf, source, out_dir, params, max_charts=int(args.max_charts)))

    pd.DataFrame(summaries).drop(columns=["state_counts"], errors="ignore").to_csv(out_dir / "summary.csv", index=False)
    (out_dir / "state_counts.json").write_text(
        json.dumps({f"{s['timeframe']}:{s['market']}": s["state_counts"] for s in summaries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_root_summary(out_dir, params, summaries)
    print(f"WROTE {out_dir}")


if __name__ == "__main__":
    main()
