"""Monthly-open extension **mean band** fade study on 1h bars.

Phase 1 — **working band** (per market, monthly ATR @ prior month close):

  For each calendar month after the opening week, measure upward / downward
  extension from month open in ATR units at every 1h bar.  Summarize per month:

  - min / median / max upward extension
  - min / median / max downward extension

  The working band on each side spans ``mean(min) … mean(max)`` with
  ``mean(median)`` inside the band.

Phase 2 — **fade backtest** (full timeline, default US30 / NQ / YM):

  - When price **falls into** the lower band (``dn_ext`` crosses ``≥ mean_min_dn``):
    **long 10** at the inner band edge; **SL** at the outer extreme
    (``month_open − mean_max_dn × ATR``).
  - When price **rises into** the upper band (``up_ext`` crosses ``≥ mean_min_up``):
    **short 10**; **SL** at ``month_open + mean_max_up × ATR``.
  - Target = month open; flatten any runner at month end.
  - Max one long and one short per month.

Hub: ``live/state/monthly_open_atr_extension_band/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import ATR_LEN, NY, wilder_atr
from .monthly_atr4_helpers import load_1h, month_windows, opening_week_slice
from .monthly_open_atr_extension_study import (
    _monthly_atr_lookup,
    _resample_monthly_ohlc,
    _week_end,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import ALL_SYMBOLS, MARKETS, MarketSpec
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_open_atr_extension_band"
DEFAULT_SYMBOLS = ("US30", "NQ", "YM")
ENTRY_QTY = 10
MIN_BAND_MONTHS = 12
DEFAULT_ROLLING_BAND_MONTHS = 6

# Entry modes (ATR extension from month open):
#   inner — fade at mean(min); SL at mean(max)  [baseline inner edge]
#   mid   — fade at mean(median); SL at mean(max)
#   max   — fade at mean(max); SL max + 20% of band width (max−min)
#   pct75 — fade at min + 75%·(max−min); SL at mean(max)
ENTRY_MODES = ("inner", "mid", "max", "pct75")


@dataclass
class SideStats:
    min_atr: float
    median_atr: float
    max_atr: float


@dataclass
class MonthPathStats:
    market: str
    year: int
    month: int
    month_open: float
    atr14: float
    up: SideStats
    dn: SideStats


@dataclass
class WorkingBand:
    market: str
    n_months: int
    up_min: float
    up_median: float
    up_max: float
    dn_min: float
    dn_median: float
    dn_max: float


@dataclass
class TradeRow:
    market: str
    year: int
    month: int
    side: str
    entry_ts: str
    entry_px: float
    stop_px: float
    target_px: float
    exit_ts: str
    exit_px: float
    exit_reason: str
    qty: int
    pnl_pts: float
    pnl_usd: float
    band_mode: str
    entry_mode: str = "inner"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _side_stats(values: np.ndarray) -> SideStats:
    v = values[np.isfinite(values)]
    if len(v) == 0:
        return SideStats(float("nan"), float("nan"), float("nan"))
    return SideStats(float(np.min(v)), float(np.median(v)), float(np.max(v)))


def _month_path_stats(
    market: MarketSpec,
    bars: pd.DataFrame,
    year: int,
    month: int,
    m0: pd.Timestamp,
    m1: pd.Timestamp,
    monthly_atr_lookup: Dict[Tuple[int, int], float],
) -> Optional[MonthPathStats]:
    month_bars = bars[(bars.index >= m0) & (bars.index < m1)]
    if month_bars.empty:
        return None
    month_open = float(month_bars["open"].iloc[0])
    ow = opening_week_slice(bars, m0)
    if ow.empty:
        return None
    atr14 = float(monthly_atr_lookup.get((year, month), float("nan")))
    if not (atr14 > 0) or pd.isna(atr14):
        return None

    _, w1 = _week_end(m0)
    watch = bars[(bars.index >= max(w1, m0)) & (bars.index < m1)]
    if watch.empty:
        return None

    up = (watch["high"].to_numpy(dtype=float) - month_open) / atr14
    dn = (month_open - watch["low"].to_numpy(dtype=float)) / atr14
    up = np.clip(up, 0.0, None)
    dn = np.clip(dn, 0.0, None)
    return MonthPathStats(
        market=market.symbol,
        year=year,
        month=month,
        month_open=month_open,
        atr14=atr14,
        up=_side_stats(up),
        dn=_side_stats(dn),
    )


def collect_path_stats(
    market: MarketSpec,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[MonthPathStats]:
    bars = load_1h(market)
    monthly_lookup = _monthly_atr_lookup(bars)
    rows: List[MonthPathStats] = []
    for year, month, m0, m1 in month_windows(bars, start, end):
        row = _month_path_stats(market, bars, year, month, m0, m1, monthly_lookup)
        if row is not None:
            rows.append(row)
    return rows


def working_band_from_paths(paths: Sequence[MonthPathStats], market: str) -> WorkingBand:
    if not paths:
        return WorkingBand(market, 0, *([float("nan")] * 6))
    up_min = float(np.mean([p.up.min_atr for p in paths]))
    up_med = float(np.mean([p.up.median_atr for p in paths]))
    up_max = float(np.mean([p.up.max_atr for p in paths]))
    dn_min = float(np.mean([p.dn.min_atr for p in paths]))
    dn_med = float(np.mean([p.dn.median_atr for p in paths]))
    dn_max = float(np.mean([p.dn.max_atr for p in paths]))
    return WorkingBand(
        market=market,
        n_months=len(paths),
        up_min=up_min,
        up_median=up_med,
        up_max=up_max,
        dn_min=dn_min,
        dn_median=dn_med,
        dn_max=dn_max,
    )


def _band_from_working(b: WorkingBand) -> Tuple[float, float, float, float, float, float]:
    return b.up_min, b.up_median, b.up_max, b.dn_min, b.dn_median, b.dn_max


def _entry_stop_atr(
    band_min: float,
    band_med: float,
    band_max: float,
    *,
    entry_mode: str,
    sl_mode: Optional[str] = None,
) -> Tuple[float, float]:
    """Return (entry_atr, stop_atr) extension from month open for one band side."""
    if not (band_max >= band_min > 0) or not all(np.isfinite(x) for x in (band_min, band_med, band_max)):
        return float("nan"), float("nan")
    width = band_max - band_min
    mode = str(entry_mode).lower()
    if mode == "inner":
        entry_atr = band_min
        stop_atr = band_max
    elif mode == "mid":
        entry_atr = band_med
        stop_atr = band_max
    elif mode == "max":
        entry_atr = band_max
        # plus_X → SL at max + X·band_width (default 0.20). Also accept band_X.
        sm = str(sl_mode or "plus_0.2").lower().strip()
        if sm in ("mean_max", "default", ""):
            frac = 0.20
        elif sm.startswith("plus_") or sm.startswith("band_"):
            try:
                frac = float(sm.split("_", 1)[1])
            except ValueError as exc:
                raise ValueError("Bad max SL mode %r (want plus_0.3)" % sm) from exc
        else:
            raise ValueError("Bad max SL mode %r (want plus_0.2 / plus_0.3)" % sm)
        stop_atr = band_max + float(frac) * width
    elif mode == "pct75":
        entry_atr = band_min + 0.75 * width
        sm = str(sl_mode or "mean_max").lower()
        # wide_Nx → SL at max + N×(max−entry); e.g. wide_2x, wide_2.5x
        if sm.startswith("wide_"):
            try:
                mult = float(sm[len("wide_") :].rstrip("xX"))
            except ValueError as exc:
                raise ValueError("Bad wide SL mode %r" % sm) from exc
            stop_atr = band_max + float(mult) * (band_max - entry_atr)
        else:
            stop_atr = band_max
    else:
        raise ValueError("Unknown entry_mode %r (want %s)" % (entry_mode, ", ".join(ENTRY_MODES)))
    if not (stop_atr > entry_atr > 0):
        return float("nan"), float("nan")
    return float(entry_atr), float(stop_atr)


def rolling_band_from_paths(
    paths: Sequence[MonthPathStats],
    market: str,
    year: int,
    month: int,
    *,
    window: int,
) -> Optional[WorkingBand]:
    prior = [p for p in paths if (p.year, p.month) < (year, month)]
    if len(prior) < int(window):
        return None
    recent = prior[-int(window) :]
    return working_band_from_paths(recent, market)


def _simulate_side(
    *,
    market: MarketSpec,
    side: str,
    watch: pd.DataFrame,
    month_open: float,
    atr14: float,
    entry_atr: float,
    stop_atr: float,
    year: int,
    month: int,
    band_mode: str,
    entry_mode: str = "inner",
) -> Optional[TradeRow]:
    if not (entry_atr > 0) or not (stop_atr > entry_atr) or not np.isfinite(entry_atr):
        return None

    if side == "long":
        entry_px = month_open - entry_atr * atr14
        stop_px = month_open - stop_atr * atr14
        target_px = month_open
        for ts, hi, lo in zip(watch.index, watch["high"], watch["low"]):
            lo_f = float(lo)
            hi_f = float(hi)
            if lo_f > entry_px:
                continue
            fill_px = min(entry_px, hi_f)
            if lo_f <= stop_px:
                return TradeRow(
                    market=market.symbol,
                    year=year,
                    month=month,
                    side=side,
                    entry_ts=ts.isoformat(),
                    entry_px=fill_px,
                    stop_px=stop_px,
                    target_px=target_px,
                    exit_ts=ts.isoformat(),
                    exit_px=stop_px,
                    exit_reason="stop",
                    qty=ENTRY_QTY,
                    pnl_pts=stop_px - fill_px,
                    pnl_usd=(stop_px - fill_px) * market.point_value * ENTRY_QTY,
                    band_mode=band_mode,
                    entry_mode=entry_mode,
                )
            after = watch[watch.index >= ts]
            for ts2, hi2, lo2, cl2 in zip(
                after.index, after["high"], after["low"], after["close"]
            ):
                if float(lo2) <= stop_px:
                    return TradeRow(
                        market=market.symbol,
                        year=year,
                        month=month,
                        side=side,
                        entry_ts=ts.isoformat(),
                        entry_px=fill_px,
                        stop_px=stop_px,
                        target_px=target_px,
                        exit_ts=ts2.isoformat(),
                        exit_px=stop_px,
                        exit_reason="stop",
                        qty=ENTRY_QTY,
                        pnl_pts=stop_px - fill_px,
                        pnl_usd=(stop_px - fill_px) * market.point_value * ENTRY_QTY,
                        band_mode=band_mode,
                    entry_mode=entry_mode,
                    )
                if float(hi2) >= target_px:
                    return TradeRow(
                        market=market.symbol,
                        year=year,
                        month=month,
                        side=side,
                        entry_ts=ts.isoformat(),
                        entry_px=fill_px,
                        stop_px=stop_px,
                        target_px=target_px,
                        exit_ts=ts2.isoformat(),
                        exit_px=target_px,
                        exit_reason="target_open",
                        qty=ENTRY_QTY,
                        pnl_pts=target_px - fill_px,
                        pnl_usd=(target_px - fill_px) * market.point_value * ENTRY_QTY,
                        band_mode=band_mode,
                    entry_mode=entry_mode,
                    )
            eom = float(watch["close"].iloc[-1])
            return TradeRow(
                market=market.symbol,
                year=year,
                month=month,
                side=side,
                entry_ts=ts.isoformat(),
                entry_px=fill_px,
                stop_px=stop_px,
                target_px=target_px,
                exit_ts=watch.index[-1].isoformat(),
                exit_px=eom,
                exit_reason="eom",
                qty=ENTRY_QTY,
                pnl_pts=eom - fill_px,
                pnl_usd=(eom - fill_px) * market.point_value * ENTRY_QTY,
                band_mode=band_mode,
                entry_mode=entry_mode,
            )
        return None

    if side == "short":
        entry_px = month_open + entry_atr * atr14
        stop_px = month_open + stop_atr * atr14
        target_px = month_open
        for ts, hi, lo in zip(watch.index, watch["high"], watch["low"]):
            hi_f = float(hi)
            lo_f = float(lo)
            if hi_f < entry_px:
                continue
            fill_px = max(entry_px, lo_f)
            if hi_f >= stop_px:
                return TradeRow(
                    market=market.symbol,
                    year=year,
                    month=month,
                    side=side,
                    entry_ts=ts.isoformat(),
                    entry_px=fill_px,
                    stop_px=stop_px,
                    target_px=target_px,
                    exit_ts=ts.isoformat(),
                    exit_px=stop_px,
                    exit_reason="stop",
                    qty=ENTRY_QTY,
                    pnl_pts=fill_px - stop_px,
                    pnl_usd=(fill_px - stop_px) * market.point_value * ENTRY_QTY,
                    band_mode=band_mode,
                    entry_mode=entry_mode,
                )
            after = watch[watch.index >= ts]
            for ts2, hi2, lo2, cl2 in zip(after.index, after["high"], after["low"], after["close"]):
                if float(hi2) >= stop_px:
                    return TradeRow(
                        market=market.symbol,
                        year=year,
                        month=month,
                        side=side,
                        entry_ts=ts.isoformat(),
                        entry_px=fill_px,
                        stop_px=stop_px,
                        target_px=target_px,
                        exit_ts=ts2.isoformat(),
                        exit_px=stop_px,
                        exit_reason="stop",
                        qty=ENTRY_QTY,
                        pnl_pts=fill_px - stop_px,
                        pnl_usd=(fill_px - stop_px) * market.point_value * ENTRY_QTY,
                        band_mode=band_mode,
                    entry_mode=entry_mode,
                    )
                if float(lo2) <= target_px:
                    return TradeRow(
                        market=market.symbol,
                        year=year,
                        month=month,
                        side=side,
                        entry_ts=ts.isoformat(),
                        entry_px=fill_px,
                        stop_px=stop_px,
                        target_px=target_px,
                        exit_ts=ts2.isoformat(),
                        exit_px=target_px,
                        exit_reason="target_open",
                        qty=ENTRY_QTY,
                        pnl_pts=fill_px - target_px,
                        pnl_usd=(fill_px - target_px) * market.point_value * ENTRY_QTY,
                        band_mode=band_mode,
                    entry_mode=entry_mode,
                    )
            eom = float(watch["close"].iloc[-1])
            return TradeRow(
                market=market.symbol,
                year=year,
                month=month,
                side=side,
                entry_ts=ts.isoformat(),
                entry_px=fill_px,
                stop_px=stop_px,
                target_px=target_px,
                exit_ts=watch.index[-1].isoformat(),
                exit_px=eom,
                exit_reason="eom",
                qty=ENTRY_QTY,
                pnl_pts=fill_px - eom,
                pnl_usd=(fill_px - eom) * market.point_value * ENTRY_QTY,
                band_mode=band_mode,
                entry_mode=entry_mode,
            )
        return None

    return None


def backtest_market(
    market: MarketSpec,
    paths: Sequence[MonthPathStats],
    *,
    band_mode: str,
    fixed_band: Optional[WorkingBand] = None,
    entry_mode: str = "inner",
    sl_mode: Optional[str] = None,
    rolling_window: Optional[int] = None,
) -> List[TradeRow]:
    bars = load_1h(market)
    monthly_lookup = _monthly_atr_lookup(bars)
    trades: List[TradeRow] = []
    by_key = {(p.year, p.month): p for p in paths}

    for year, month, m0, m1 in month_windows(bars, None, None):
        path = by_key.get((year, month))
        if path is None:
            continue
        if band_mode == "fixed":
            if fixed_band is None:
                continue
            up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(fixed_band)
        elif band_mode == "rolling":
            wb = rolling_band_from_paths(
                paths,
                market.symbol,
                year,
                month,
                window=int(rolling_window or DEFAULT_ROLLING_BAND_MONTHS),
            )
            if wb is None:
                continue
            up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(wb)
        else:
            prior = [p for p in paths if (p.year, p.month) < (year, month)]
            if len(prior) < MIN_BAND_MONTHS:
                continue
            wb = working_band_from_paths(prior, market.symbol)
            up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(wb)

        dn_entry, dn_stop = _entry_stop_atr(
            dn_min, dn_med, dn_max, entry_mode=entry_mode, sl_mode=sl_mode
        )
        up_entry, up_stop = _entry_stop_atr(
            up_min, up_med, up_max, entry_mode=entry_mode, sl_mode=sl_mode
        )

        _, w1 = _week_end(m0)
        watch = bars[(bars.index >= max(w1, m0)) & (bars.index < m1)]
        if watch.empty:
            continue

        long_tr = _simulate_side(
            market=market,
            side="long",
            watch=watch,
            month_open=path.month_open,
            atr14=path.atr14,
            entry_atr=dn_entry,
            stop_atr=dn_stop,
            year=year,
            month=month,
            band_mode=band_mode,
            entry_mode=entry_mode,
        )
        if long_tr is not None:
            trades.append(long_tr)

        short_tr = _simulate_side(
            market=market,
            side="short",
            watch=watch,
            month_open=path.month_open,
            atr14=path.atr14,
            entry_atr=up_entry,
            stop_atr=up_stop,
            year=year,
            month=month,
            band_mode=band_mode,
            entry_mode=entry_mode,
        )
        if short_tr is not None:
            trades.append(short_tr)
    return trades


def _band_md(bands: Dict[str, WorkingBand]) -> str:
    lines = [
        "# Monthly open extension — working band",
        "",
        "ATR: **monthly Wilder ATR(14)** @ prior month close.",
        "Extension window: after opening week through month end.",
        "",
        "Each side band spans **mean(min) → mean(max)** ATR extension with",
        "**mean(median)** inside. Entry at inner edge; SL at outer extreme.",
        "",
        "| Market | N months | Up min | Up med | Up max | Dn min | Dn med | Dn max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sym, b in sorted(bands.items()):
        lines.append(
            "| %s | %d | %.3f× | %.3f× | %.3f× | %.3f× | %.3f× | %.3f× |"
            % (sym, b.n_months, b.up_min, b.up_median, b.up_max, b.dn_min, b.dn_median, b.dn_max)
        )
    lines.extend(
        [
            "",
            "## Price levels (example: current band × monthly ATR)",
            "",
            "At month open `O` and monthly ATR `A`:",
            "",
            "- **Long band:** `[O − dn_max·A, O − dn_min·A]` — buy at `O − dn_min·A`, SL `O − dn_max·A`",
            "- **Short band:** `[O + up_min·A, O + up_max·A]` — sell at `O + up_min·A`, SL `O + up_max·A`",
            "- Target: month open `O`; flatten runner at EOM if still open.",
        ]
    )
    return "\n".join(lines) + "\n"


def _summary_md(
    bands: Dict[str, WorkingBand],
    trades_fixed: pd.DataFrame,
    trades_expanding: pd.DataFrame,
) -> str:
    lines = [
        "# Monthly open extension band fade — backtest summary",
        "",
        "Qty **10** per entry. Monthly ATR. Target = month open.",
        "",
        "## Working band (full history)",
        "",
    ]
    lines.append(_band_md(bands).split("\n", 1)[1].strip())
    lines.extend(["", "## Backtest results", ""])

    def _block(df: pd.DataFrame, title: str) -> None:
        lines.append("### %s" % title)
        lines.append("")
        if df.empty:
            lines.append("_No trades._")
            lines.append("")
            return
        lines.append(
            "| Market | Trades | Win% | Net USD | Avg pts | Stop% | Target% | EOM% |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for sym, g in df.groupby("market", sort=True):
            n = len(g)
            win = float((g.pnl_usd > 0).mean())
            net = float(g.pnl_usd.sum())
            avg_pts = float(g.pnl_pts.mean())
            reasons = g.exit_reason.value_counts(normalize=True)
            lines.append(
                "| %s | %d | %.1f%% | %s | %.1f | %.0f%% | %.0f%% | %.0f%% |"
                % (
                    sym,
                    n,
                    100.0 * win,
                    "{:,.0f}".format(net),
                    avg_pts,
                    100.0 * reasons.get("stop", 0.0),
                    100.0 * reasons.get("target_open", 0.0),
                    100.0 * reasons.get("eom", 0.0),
                )
            )
        tot = float(df.pnl_usd.sum())
        lines.append("")
        lines.append("**Portfolio net:** $%s (%d trades)" % ("{:,.0f}".format(tot), len(df)))
        lines.append("")

    _block(trades_fixed, "Fixed band (full-history means — in-sample)")
    _block(trades_expanding, "Expanding band (causal — prior months only, min %d)" % MIN_BAND_MONTHS)
    return "\n".join(lines) + "\n"


def _entry_mode_blurb(entry_mode: str) -> str:
    mode = str(entry_mode).lower()
    if mode == "inner":
        return "Entry at mean(min); SL at mean(max)."
    if mode == "mid":
        return "Entry at mean(median); SL at mean(max)."
    if mode == "max":
        return "Entry at mean(max); SL max + 20% of band width."
    if mode == "pct75":
        return "Entry at min + 75%·(max−min); SL at mean(max)."
    return "entry_mode=%s" % mode


def _sl_mode_blurb(entry_mode: str, sl_mode: Optional[str] = None) -> str:
    mode = str(entry_mode).lower()
    sm = str(sl_mode or "mean_max").lower()
    if mode == "max":
        frac = 0.20
        if sm.startswith("plus_") or sm.startswith("band_"):
            try:
                frac = float(sm.split("_", 1)[1])
            except ValueError:
                frac = 0.20
        return "Entry at mean(max); SL max + {0:g}% of band width.".format(100.0 * frac)
    if mode == "pct75" and sm.startswith("wide_"):
        try:
            mult = float(sm[len("wide_") :].rstrip("xX"))
        except ValueError:
            mult = float("nan")
        return "Entry at min + 75%·(max−min); SL max + {0:g}×(max−entry).".format(mult)
    return _entry_mode_blurb(entry_mode)


def build_month_plans(
    market: MarketSpec,
    *,
    entry_mode: str = "pct75",
    sl_mode: str = "mean_max",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    start: Optional[date] = None,
    end: Optional[date] = None,
    watch_start_mode: str = "post_week1",
) -> Dict[str, dict]:
    """Causal monthly band plans for Engine replay (rolling band).

    ``watch_start_mode``:
      - ``post_week1`` (default): arm after opening week (legacy fade window)
      - ``month_open``: watch from first bar of the month (week-1 OHLC filters)
    """
    paths = collect_path_stats(market, start=start, end=end)
    bars = load_1h(market)
    plans: Dict[str, dict] = {}
    wmode = str(watch_start_mode or "post_week1").lower()
    for year, month, m0, m1 in month_windows(bars, start, end):
        wb = rolling_band_from_paths(
            paths,
            market.symbol,
            year,
            month,
            window=int(rolling_window),
        )
        path = next((p for p in paths if p.year == year and p.month == month), None)
        if wb is None or path is None:
            continue
        up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(wb)
        dn_entry, dn_stop = _entry_stop_atr(
            dn_min,
            dn_med,
            dn_max,
            entry_mode=entry_mode,
            sl_mode=sl_mode,
        )
        up_entry, up_stop = _entry_stop_atr(
            up_min,
            up_med,
            up_max,
            entry_mode=entry_mode,
            sl_mode=sl_mode,
        )
        _, w1 = _week_end(m0)
        if wmode in {"month_open", "month_start", "m0"}:
            watch_start = m0
        else:
            watch_start = max(w1, m0)
        mo = float(path.month_open)
        atr = float(path.atr14)
        key = "%04d-%02d" % (year, month)
        long_side = None
        if np.isfinite(dn_entry) and dn_stop > dn_entry > 0:
            long_side = {
                "entry": mo - dn_entry * atr,
                "stop": mo - dn_stop * atr,
                "target": mo,
                "med": mo - dn_med * atr,
                "band_max": mo - dn_max * atr,
            }
        short_side = None
        if np.isfinite(up_entry) and up_stop > up_entry > 0:
            short_side = {
                "entry": mo + up_entry * atr,
                "stop": mo + up_stop * atr,
                "target": mo,
                "med": mo + up_med * atr,
                "band_max": mo + up_max * atr,
            }
        plans[key] = {
            "year": year,
            "month": month,
            "month_open": mo,
            "atr14": atr,
            "watch_start_ts": watch_start.tz_convert("UTC").isoformat().replace("+00:00", "Z"),
            "month_end_ts": m1.tz_convert("UTC").isoformat().replace("+00:00", "Z"),
            "long": long_side,
            "short": short_side,
        }
    return plans


def _variant_summary_md(
    *,
    entry_mode: str,
    rolling_window: int,
    trades: pd.DataFrame,
) -> str:
    lines = [
        "# Monthly open extension band fade — %s / rolling-%dm" % (entry_mode, rolling_window),
        "",
        "Qty **%d** per entry. Monthly ATR. Target = month open." % ENTRY_QTY,
        "",
        _entry_mode_blurb(entry_mode),
        "Band: **6-month rolling** mean(min/med/max) on prior months (min %d warmup)."
        % MIN_BAND_MONTHS,
        "",
        "## NQ results",
        "",
    ]
    sub = trades[trades["market"] == "NQ"] if not trades.empty and "market" in trades.columns else trades
    if sub.empty:
        lines.append("_No trades._")
    else:
        n = len(sub)
        win = float((sub.pnl_usd > 0).mean())
        net = float(sub.pnl_usd.sum())
        avg_pts = float(sub.pnl_pts.mean())
        reasons = sub.exit_reason.value_counts(normalize=True)
        lines.extend(
            [
                "| Trades | Win% | Net USD | Avg pts | Stop% | Target% | EOM% |",
                "|---:|---:|---:|---:|---:|---:|---:|",
                "| %d | %.1f%% | %s | %.1f | %.0f%% | %.0f%% | %.0f%% |"
                % (
                    n,
                    100.0 * win,
                    "{:,.0f}".format(net),
                    avg_pts,
                    100.0 * reasons.get("stop", 0.0),
                    100.0 * reasons.get("target_open", 0.0),
                    100.0 * reasons.get("eom", 0.0),
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def build_variant(
    *,
    output_root: Path,
    symbols: Sequence[str],
    start: Optional[date],
    end: Optional[date],
    entry_mode: str,
    rolling_window: int,
    email: bool,
) -> None:
    entry_mode = str(entry_mode).lower()
    if entry_mode not in ENTRY_MODES:
        raise SystemExit("Unknown entry_mode %r (want %s)" % (entry_mode, ", ".join(ENTRY_MODES)))

    output_root.mkdir(parents=True, exist_ok=True)
    path_rows: List[dict] = []
    all_trades: List[TradeRow] = []

    try:
        for sym in symbols:
            sym = sym.upper()
            if sym not in MARKETS:
                raise SystemExit("Unknown market %s" % sym)
            spec = MARKETS[sym]
            _progress(output_root, "PATHS %s entry=%s rolling=%d" % (sym, entry_mode, rolling_window))
            paths = collect_path_stats(spec, start=start, end=end)
            for p in paths:
                path_rows.append(
                    {
                        "market": p.market,
                        "year": p.year,
                        "month": p.month,
                        "month_open": p.month_open,
                        "atr14": p.atr14,
                        "up_min_atr": p.up.min_atr,
                        "up_median_atr": p.up.median_atr,
                        "up_max_atr": p.up.max_atr,
                        "dn_min_atr": p.dn.min_atr,
                        "dn_median_atr": p.dn.median_atr,
                        "dn_max_atr": p.dn.max_atr,
                    }
                )
            trades = backtest_market(
                spec,
                paths,
                band_mode="rolling",
                entry_mode=entry_mode,
                rolling_window=rolling_window,
            )
            all_trades.extend(trades)
            _progress(output_root, "DONE %s trades=%d" % (sym, len(trades)))

        pd.DataFrame(path_rows).to_csv(output_root / "month_paths.csv", index=False)
        df = pd.DataFrame([asdict(t) for t in all_trades])
        df.to_csv(output_root / "trades.csv", index=False)

        summary = _variant_summary_md(
            entry_mode=entry_mode,
            rolling_window=rolling_window,
            trades=df,
        )
        (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")

        nq = df[df["market"] == "NQ"] if not df.empty else df
        nq_net = float(nq.pnl_usd.sum()) if not nq.empty else 0.0
        email_body = "\n".join(
            [
                "potions: monthly open extension band — NQ %s / rolling-%dm"
                % (entry_mode, rolling_window),
                "",
                "Hub: %s" % output_root,
                "Markets: %s" % ", ".join(s.upper() for s in symbols),
                "Entry: %s" % _entry_mode_blurb(entry_mode),
                "Band: %d-month rolling mean(min/med/max)" % rolling_window,
                "",
                summary,
            ]
        )
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "entry_mode": entry_mode,
                    "rolling_window": rolling_window,
                    "markets": list(symbols),
                    "trades": len(df),
                    "nq_trades": len(nq),
                    "nq_net_usd": nq_net,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        hub_rel = output_root.resolve().relative_to(REPO)
        log_run(
            run_class="pandas",
            variant_slug="monthly_open_atr_extension_band_%s_r%dm" % (entry_mode, rolling_window),
            instrument=",".join(s.upper() for s in symbols),
            hub_path=str(hub_rel),
            net_usd=nq_net,
            trades=len(nq),
            meta={"entry_mode": entry_mode, "rolling_window": rolling_window},
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: extension band variant FAILED (%s)\n\nHub: %s\n\n%s\n"
            % (entry_mode, output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: extension band variant FAILED (%s)" % entry_mode,
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ extension band %s rolling-%dm — net $%s"
            % (entry_mode, rolling_window, "{:,.0f}".format(nq_net)),
            body=email_body,
        )
        _progress(output_root, "email sent")


def build(
    *,
    output_root: Path,
    symbols: Sequence[str],
    start: Optional[date],
    end: Optional[date],
    email: bool,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    path_rows: List[dict] = []
    bands: Dict[str, WorkingBand] = {}
    all_fixed: List[TradeRow] = []
    all_expanding: List[TradeRow] = []

    try:
        for sym in symbols:
            sym = sym.upper()
            if sym not in MARKETS:
                raise SystemExit("Unknown market %s" % sym)
            spec = MARKETS[sym]
            _progress(output_root, "PATHS %s" % sym)
            paths = collect_path_stats(spec, start=start, end=end)
            for p in paths:
                path_rows.append(
                    {
                        "market": p.market,
                        "year": p.year,
                        "month": p.month,
                        "month_open": p.month_open,
                        "atr14": p.atr14,
                        "up_min_atr": p.up.min_atr,
                        "up_median_atr": p.up.median_atr,
                        "up_max_atr": p.up.max_atr,
                        "dn_min_atr": p.dn.min_atr,
                        "dn_median_atr": p.dn.median_atr,
                        "dn_max_atr": p.dn.max_atr,
                    }
                )
            band = working_band_from_paths(paths, sym)
            bands[sym] = band
            _progress(
                output_root,
                "BAND %s up=[%.3f, %.3f, %.3f] dn=[%.3f, %.3f, %.3f] n=%d"
                % (sym, band.up_min, band.up_median, band.up_max, band.dn_min, band.dn_median, band.dn_max, band.n_months),
            )

            _progress(output_root, "BACKTEST fixed %s" % sym)
            fixed = backtest_market(spec, paths, band_mode="fixed", fixed_band=band)
            all_fixed.extend(fixed)
            _progress(output_root, "BACKTEST expanding %s trades=%d/%d" % (sym, len(fixed), len(all_fixed)))

            expanding = backtest_market(spec, paths, band_mode="expanding")
            all_expanding.extend(expanding)
            _progress(output_root, "DONE %s expanding_trades=%d" % (sym, len(expanding)))

        pd.DataFrame(path_rows).to_csv(output_root / "month_paths.csv", index=False)
        pd.DataFrame([asdict(b) for b in bands.values()]).to_csv(output_root / "working_band.csv", index=False)
        (output_root / "BAND.md").write_text(_band_md(bands), encoding="utf-8")

        df_fixed = pd.DataFrame([asdict(t) for t in all_fixed])
        df_exp = pd.DataFrame([asdict(t) for t in all_expanding])
        df_fixed.to_csv(output_root / "trades_fixed_band.csv", index=False)
        df_exp.to_csv(output_root / "trades_expanding_band.csv", index=False)

        summary = _summary_md(bands, df_fixed, df_exp)
        (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")

        port_fixed = float(df_fixed.pnl_usd.sum()) if not df_fixed.empty else 0.0
        port_exp = float(df_exp.pnl_usd.sum()) if not df_exp.empty else 0.0
        email_body = "\n".join(
            [
                "potions: monthly open extension band fade complete",
                "",
                "Hub: %s" % output_root,
                "Markets: %s" % ", ".join(s.upper() for s in symbols),
                "Qty: %d | Target: month open | SL: band extreme" % ENTRY_QTY,
                "",
                summary,
            ]
        )
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "markets": list(symbols),
                    "fixed_trades": len(df_fixed),
                    "expanding_trades": len(df_exp),
                    "fixed_net_usd": port_fixed,
                    "expanding_net_usd": port_exp,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        log_run(
            run_class="pandas",
            variant_slug="monthly_open_atr_extension_band",
            instrument=",".join(s.upper() for s in symbols),
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=port_exp,
            trades=len(df_exp),
            meta={"fixed_net_usd": port_fixed, "band_mode": "expanding_primary"},
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: monthly open extension band FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: monthly open extension band FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: monthly open ATR extension band fade — net $%s"
            % ("{:,.0f}".format(port_exp)),
            body=email_body,
        )
        _progress(output_root, "email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symbol", action="append", dest="symbols", help="Repeatable; default US30 NQ YM")
    ap.add_argument("--start", type=lambda s: date.fromisoformat(s), default=None)
    ap.add_argument("--end", type=lambda s: date.fromisoformat(s), default=None)
    ap.add_argument(
        "--entry-mode",
        choices=ENTRY_MODES,
        default=None,
        help="If set, run single variant with --band-mode rolling (default window 6m)",
    )
    ap.add_argument(
        "--rolling-window",
        type=int,
        default=DEFAULT_ROLLING_BAND_MONTHS,
        help="Rolling band months when --entry-mode is set (default 6)",
    )
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbols or list(DEFAULT_SYMBOLS)
    if args.entry_mode:
        build_variant(
            output_root=args.output_root,
            symbols=symbols,
            start=args.start,
            end=args.end,
            entry_mode=str(args.entry_mode),
            rolling_window=int(args.rolling_window),
            email=bool(args.email),
        )
    else:
        build(
            output_root=args.output_root,
            symbols=symbols,
            start=args.start,
            end=args.end,
            email=bool(args.email),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
