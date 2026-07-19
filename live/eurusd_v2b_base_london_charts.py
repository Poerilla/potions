"""EURUSD v2b base charts: London open → NY close with OR + London H/L.

Samples ~200 trades from the last 5 years of the overnight ungated
``eurusd_v2b_oco_S_1_1_3`` book. Each chart uses 5m candles covering the
London killzone through NY cash close, and overlays:

- v2b opening range (09:30–09:45 NY) as a shaded band + high/low lines
- London killzone high/low (**02:00–05:00 America/New_York**)
- entry / TP / stop markers from PaperBroker fills
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_prior_opposed_5m_charts import _resample_5m, _select_trades
from .fx_data import load_fx_1m_by_ny_date
from .nq_v2b_prior_opposed_15m_charts import (
    _draw_v2b_trade,
    _load_v2b_fill_groups,
    _load_v2b_trades,
    _plot_candles,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
LDN = "Europe/London"
NY_TZ = pytz.timezone(NY)
LDN_TZ = pytz.timezone(LDN)
INSTRUMENT = "EURUSD"
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0

LONDON_OPEN = time(8, 0)
NY_CLOSE = time(16, 0)
# London killzone used for session high/low (NY wall clock).
LONDON_KZ_START = time(2, 0)
LONDON_KZ_END = time(5, 0)
OR_START = time(9, 30)
OR_END = time(9, 45)


def _session_bounds(session: date) -> Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Return (london_open_ny, london_kz_start, london_kz_end, ny_close_ny)."""
    london_open = LDN_TZ.localize(datetime.combine(session, LONDON_OPEN)).astimezone(NY_TZ)
    kz_start = NY_TZ.localize(datetime.combine(session, LONDON_KZ_START))
    kz_end = NY_TZ.localize(datetime.combine(session, LONDON_KZ_END))
    ny_close = NY_TZ.localize(datetime.combine(session, NY_CLOSE))
    return pd.Timestamp(london_open), pd.Timestamp(kz_start), pd.Timestamp(kz_end), pd.Timestamp(ny_close)


def _opening_range(df_1m: pd.DataFrame) -> Optional[Tuple[float, float, pd.Timestamp, pd.Timestamp]]:
    if df_1m.empty:
        return None
    opening = df_1m[(df_1m.index.time >= OR_START) & (df_1m.index.time < OR_END)]
    if opening.empty:
        return None
    return (
        float(opening["high"].max()),
        float(opening["low"].min()),
        opening.index[0],
        opening.index[-1] + pd.Timedelta(minutes=1),
    )


def _london_killzone_range(
    df_1m: pd.DataFrame,
    kz_start: pd.Timestamp,
    kz_end: pd.Timestamp,
) -> Optional[Tuple[float, float]]:
    """High/low of the 02:00–05:00 NY London killzone."""
    if df_1m.empty:
        return None
    london = df_1m[(df_1m.index >= kz_start) & (df_1m.index < kz_end)]
    if london.empty:
        return None
    return float(london["high"].max()), float(london["low"].min())


def _add_session_levels(
    ax,
    candles: pd.DataFrame,
    *,
    or_levels: Optional[Tuple[float, float, pd.Timestamp, pd.Timestamp]],
    london_hl: Optional[Tuple[float, float]],
    london_open: pd.Timestamp,
    kz_start: pd.Timestamp,
    kz_end: pd.Timestamp,
    ny_close: pd.Timestamp,
) -> None:
    if or_levels is not None:
        or_h, or_l, or_t0, or_t1 = or_levels
        ax.axhspan(or_l, or_h, color="#90caf9", alpha=0.22, zorder=1, label="Opening range")
        ax.axvspan(or_t0, or_t1, color="#90caf9", alpha=0.10, zorder=0)
        ax.hlines(or_h, candles.index[0], ny_close, colors="#1565c0", linestyles="-", linewidth=1.1, alpha=0.85)
        ax.hlines(or_l, candles.index[0], ny_close, colors="#1565c0", linestyles="-", linewidth=1.1, alpha=0.85)
        ax.text(candles.index[0], or_h, " OR high", color="#1565c0", fontsize=8, va="bottom")
        ax.text(candles.index[0], or_l, " OR low", color="#1565c0", fontsize=8, va="top")

    if london_hl is not None:
        ldn_h, ldn_l = london_hl
        # Extend London H/L across the visible window so they remain readable
        # after the 02:00–05:00 killzone (where the extremes formed).
        ax.axvspan(kz_start, kz_end, color="#ffcc80", alpha=0.12, zorder=0, label="London KZ 02-05 NY")
        ax.hlines(
            ldn_h,
            candles.index[0],
            ny_close,
            colors="#ef6c00",
            linestyles="--",
            linewidth=1.35,
            alpha=0.95,
            label="London high/low (02-05 NY)",
        )
        ax.hlines(ldn_l, candles.index[0], ny_close, colors="#ef6c00", linestyles="--", linewidth=1.35, alpha=0.95)
        ax.text(kz_start, ldn_h, " London high", color="#ef6c00", fontsize=8, va="bottom")
        ax.text(kz_start, ldn_l, " London low", color="#ef6c00", fontsize=8, va="top")

    ax.axvline(london_open, color="#78909c", linewidth=1.0, alpha=0.45, linestyle=":")
    ax.axvline(kz_start, color="#ef6c00", linewidth=1.0, alpha=0.55, linestyle=":")
    ax.axvline(kz_end, color="#ef6c00", linewidth=1.0, alpha=0.55, linestyle=":")
    ax.axvline(ny_close, color="#455a64", linewidth=1.0, alpha=0.55, linestyle=":")


def build_charts(
    *,
    output_root: Path,
    one_m: Path,
    v2b_fills: Path,
    max_charts: int,
    lookback_years: int,
    force: bool,
) -> None:
    import live.nq_v2b_prior_opposed_15m_charts as base

    base.POINT_VALUE = POINT_VALUE
    base.FEE_PER_UNIT = FEE_PER_UNIT

    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    all_trades = sorted(_load_v2b_trades(v2b_fills), key=lambda item: item.entry_ts)
    if not all_trades:
        raise SystemExit("No v2b trades found in %s" % v2b_fills)

    end_day = max(t.entry_ts.date() for t in all_trades)
    start_day = end_day - timedelta(days=365 * lookback_years)
    window_trades = [t for t in all_trades if t.entry_ts.date() >= start_day]
    selected = _select_trades(window_trades, max_charts)
    v2b_groups = _load_v2b_fill_groups(v2b_fills)

    print(
        "Loading EURUSD 1m for London→NY charts (%d trades, window %s → %s)..."
        % (len(selected), start_day.isoformat(), end_day.isoformat()),
        flush=True,
    )
    bars_by_day = load_fx_1m_by_ny_date(one_m, INSTRUMENT)

    rows: List[Dict[str, object]] = []
    for idx, trade in enumerate(selected, start=1):
        session = trade.entry_ts.date()
        london_open, kz_start, kz_end, ny_close = _session_bounds(session)
        # Chart starts at the earlier of London cash open vs killzone start so
        # the 02:00–05:00 NY extremes are always visible.
        chart_start = min(london_open, kz_start)

        frames = []
        prev = bars_by_day.get(session - timedelta(days=1))
        if prev is not None and not prev.empty:
            frames.append(prev)
        raw = bars_by_day.get(session)
        if raw is not None and not raw.empty:
            frames.append(raw)
        if not frames:
            continue
        merged = pd.concat(frames).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        win_1m = merged[(merged.index >= chart_start) & (merged.index < ny_close)].copy()
        if win_1m.empty:
            continue
        if "volume" not in win_1m.columns:
            win_1m["volume"] = 0.0

        candles = _resample_5m(win_1m)
        if candles.empty:
            continue
        or_levels = _opening_range(win_1m)
        london_hl = _london_killzone_range(win_1m, kz_start, kz_end)
        fills = v2b_groups[trade.trade_id]

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(17, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)
        _add_session_levels(
            ax,
            candles,
            or_levels=or_levels,
            london_hl=london_hl,
            london_open=london_open,
            kz_start=kz_start,
            kz_end=kz_end,
            ny_close=ny_close,
        )
        _draw_v2b_trade(ax, trade, fills)
        ax.set_title(
            "EURUSD v2b base S_1_1_3 — %s — %s — net $%.0f  (London KZ 02-05 NY → NY close)"
            % (session.isoformat(), trade.side, trade.net_usd)
        )
        ax.set_ylabel(INSTRUMENT)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)
        ax.set_xlim(chart_start, ny_close)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(5 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        vol_ax.set_xlim(chart_start, ny_close)
        fig.autofmt_xdate()

        rel = Path("charts") / (
            "%03d_%s_%s_%s.png" % (idx, session.isoformat(), trade.side, "win" if trade.net_usd > 0 else "loss")
        )
        out = output_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=135, bbox_inches="tight")
        plt.close(fig)

        or_h = or_levels[0] if or_levels else ""
        or_l = or_levels[1] if or_levels else ""
        ldn_h = london_hl[0] if london_hl else ""
        ldn_l = london_hl[1] if london_hl else ""
        rows.append(
            {
                "idx": idx,
                "session": session.isoformat(),
                "side": trade.side,
                "net": trade.net_usd,
                "v2b_trade_id": trade.trade_id,
                "or_high": or_h,
                "or_low": or_l,
                "london_high": ldn_h,
                "london_low": ldn_l,
                "london_kz_start": str(kz_start),
                "london_kz_end": str(kz_end),
                "ny_close": str(ny_close),
                "chart": str(rel),
            }
        )
        if idx % 25 == 0:
            print("  charted %d/%d" % (idx, len(selected)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# EURUSD v2b base — London killzone → NY close charts",
        "",
        "Ungated overnight `eurusd_v2b_oco_S_1_1_3` (v2b base). Even sample of **%d** trades from the last **%d** years (%s → %s)."
        % (len(rows), lookback_years, start_day.isoformat(), end_day.isoformat()),
        "",
        "- Window: from **min(London 08:00, 02:00 NY)** through **16:00 NY** (5m candles)",
        "- Opening range: **09:30–09:45 NY** (shaded + blue H/L)",
        "- London high/low: **02:00–05:00 America/New_York** killzone (orange dashed + amber band)",
        "- Source fills: `%s`" % v2b_fills.as_posix(),
        "",
        "| # | Session | Side | Net | OR high | OR low | London high | London low | Chart |",
        "|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${net:,.2f} | {or_high} | {or_low} | {london_high} | {london_low} | [{chart}]({chart}) |".format(
                **{
                    **item,
                    "or_high": ("%.5f" % item["or_high"]) if item["or_high"] != "" else "",
                    "or_low": ("%.5f" % item["or_low"]) if item["or_low"] != "" else "",
                    "london_high": ("%.5f" % item["london_high"]) if item["london_high"] != "" else "",
                    "london_low": ("%.5f" % item["london_low"]) if item["london_low"] != "" else "",
                }
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/eurusd_overnight_sweep/charts/v2b_base_london_ny",
    )
    parser.add_argument("--one-m", type=Path, default=REPO / "fx" / "eurusd_1m.csv")
    parser.add_argument(
        "--v2b-fills",
        type=Path,
        default=REPO / "live/state/eurusd_overnight_sweep/states/eurusd_v2b_oco_S_1_1_3/fills.csv",
    )
    parser.add_argument("--max-charts", type=int, default=200)
    parser.add_argument("--lookback-years", type=int, default=5)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(
        output_root=args.output_root,
        one_m=args.one_m,
        v2b_fills=args.v2b_fills,
        max_charts=args.max_charts,
        lookback_years=args.lookback_years,
        force=not args.no_force,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
