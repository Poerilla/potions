"""Trade charts for monthly-open extension **mean band** fades.

Reads ``trades_expanding_band.csv`` (or ``trades_fixed_band.csv``) from the
band hub and charts sampled trades with 1h candles, band levels, entry/stop/target.

Usage::

  python -m live.monthly_open_atr_extension_band_trade_charts \\
    --market NQ --count 20 --email
"""

from __future__ import annotations

import argparse
import html
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import NY, plot_candles as plot_candles_4h, price_fmt, shade_weeks, slug
from .monthly_atr4_helpers import load_1h, month_windows
from .instrument_deep_check import _resolve_paths, load_campaigns
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    MIN_BAND_MONTHS,
    _band_from_working,
    _entry_stop_atr,
    _sl_mode_blurb,
    collect_path_stats,
    rolling_band_from_paths,
    working_band_from_paths,
)
from .monthly_open_atr_extension_study import plot_candles_1h
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HUB = REPO / "live" / "state" / "monthly_open_atr_extension_band"
DEFAULT_OUT = DEFAULT_HUB / "trade_charts"

PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 18

MONTH_OPEN_COLOR = "#1565c0"
BAND_FILL = "#fff3e0"
BAND_EDGE = "#ef6c00"
BAND_MED = "#ff9800"
ENTRY_COLOR = "#6a1b9a"
STOP_COLOR = "#c62828"
TARGET_COLOR = MONTH_OPEN_COLOR
EXIT_COLOR = "#2e7d32"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _even_sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.iloc[0:0]
    if len(df) <= n:
        return df.reset_index(drop=True)
    idx = np.linspace(0, len(df) - 1, n, dtype=int)
    return df.iloc[idx].reset_index(drop=True)


def _exit_reason_label(reason: str) -> str:
    r = str(reason or "").strip().lower()
    if r == "target":
        return "target_open"
    if r == "flatten":
        return "eom"
    return r or "exit"


def _broker_trades_df(state_root: Path, market: str) -> pd.DataFrame:
    """Build trade rows from Engine+PaperBroker fills (broker-like replay)."""
    paths = _resolve_paths(state_root, None, None)
    campaigns = load_campaigns(paths)
    if campaigns.empty:
        return campaigns
    fills = pd.read_csv(paths.fills)
    orders_path = state_root / "orders.csv"
    orders = pd.read_csv(orders_path) if orders_path.exists() else pd.DataFrame()
    rows: List[dict] = []
    for camp in campaigns.itertuples(index=False):
        trade_id = str(camp.trade_id)
        trade_fills = fills[fills["trade_id"].astype(str) == trade_id].sort_values("ts")
        if trade_fills.empty:
            continue
        entry_fill = trade_fills[trade_fills["reason"].astype(str) == "entry"].iloc[0]
        exit_fills = trade_fills[trade_fills["reason"].astype(str) != "entry"]
        if exit_fills.empty:
            continue
        exit_fill = exit_fills.iloc[-1]
        entry_ts = pd.Timestamp(camp.entry_ts)
        exit_ts = pd.Timestamp(exit_fills["ts"].max())
        side = str(camp.side).lower()
        entry_px = float(entry_fill["price"])
        exit_px = float(exit_fill["price"])
        exit_reason = _exit_reason_label(str(exit_fill["reason"]))
        stop_px = float("nan")
        target_px = float("nan")
        if not orders.empty and "trade_id" in orders.columns:
            trade_orders = orders[orders["trade_id"].astype(str) == trade_id]
            stop_rows = trade_orders[trade_orders["bracket_role"].astype(str) == "stop"]
            target_rows = trade_orders[trade_orders["bracket_role"].astype(str) == "target"]
            if not stop_rows.empty and pd.notna(stop_rows.iloc[0].get("stop_price")):
                stop_px = float(stop_rows.iloc[0]["stop_price"])
            if not target_rows.empty and pd.notna(target_rows.iloc[0].get("limit_price")):
                target_px = float(target_rows.iloc[0]["limit_price"])
        rows.append(
            {
                "market": market.upper(),
                "year": int(entry_ts.year),
                "month": int(entry_ts.month),
                "side": side,
                "entry_ts": entry_ts,
                "entry_px": entry_px,
                "stop_px": stop_px,
                "target_px": target_px,
                "exit_ts": exit_ts,
                "exit_px": exit_px,
                "exit_reason": exit_reason,
                "pnl_usd": float(camp.net_usd),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "month", "entry_ts"]).reset_index(drop=True)


def _pack_png_batches(paths: List[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        sz = p.stat().st_size
        if sz > 8 * 1024 * 1024:
            continue
        overflow = cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES)
        if overflow:
            batches.append(cur)
            cur = []
            cur_bytes = 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def _email_chart_batches(
    *,
    output_root: Path,
    market: str,
    entry_mode: str,
    sl_mode: str,
    rolling_window: int,
    chart_rows: List[dict],
    blurb: str,
    source: str,
    broker_like: bool,
) -> int:
    pngs = sorted(
        {
            output_root / r["chart"]
            for r in chart_rows
            if (output_root / r["chart"]).exists()
        }
    )
    batches = _pack_png_batches(pngs)
    n_wins = sum(1 for r in chart_rows if float(r["pnl_usd"]) > 0)
    n_losses = len(chart_rows) - n_wins
    tag = "broker-like" if broker_like else "pandas"
    headline = (
        "NQ pct75 %s rolling-%dm — %s (%d charts, %d wins / %d losses). PNGs not zipped."
        % (entry_mode, rolling_window, sl_mode, len(chart_rows), n_wins, n_losses)
    )
    if not batches:
        body = "\n".join(
            [
                "potions: monthly open extension band trade charts",
                "",
                headline,
                "No PNG charts produced.",
                "Hub: %s" % output_root,
                "Source: %s" % source,
            ]
        )
        send_email(subject="potions: NQ extension band charts (none)", body=body)
        return 0
    n_sent = 0
    for bi, batch in enumerate(batches, start=1):
        names = [p.name for p in batch]
        body = "\n".join(
            [
                "potions: monthly open extension band trade charts (%d/%d)" % (bi, len(batches)),
                "",
                headline,
                blurb,
                "",
                "This email: %d of %d charts." % (len(batch), len(pngs)),
                "Hub: %s" % output_root,
                "Source: %s" % source,
                "",
                "Attached: " + ", ".join(names[:10]) + (" …" if len(names) > 10 else ""),
            ]
        )
        batch_names = {p.name for p in batch}
        rows_html = "\n".join(
            "<tr><td>%04d-%02d</td><td>%s</td><td>%s</td><td>%+.0f</td></tr>"
            % (r["year"], r["month"], r["side"], r["exit_reason"], r["pnl_usd"])
            for r in chart_rows
            if Path(r["chart"]).name in batch_names
        )
        html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>%s band fade charts — %s %s</h2>
<p>%s</p>
<p>Email %d/%d — %d PNG attachments (not zipped).</p>
<p>Hub <code>%s</code></p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>month</th><th>side</th><th>exit</th><th>pnl</th></tr>
%s
</table></body></html>""" % (
            html.escape(market.upper()),
            html.escape(entry_mode),
            html.escape(sl_mode),
            html.escape(headline + "\n" + blurb),
            bi,
            len(batches),
            len(batch),
            html.escape(str(output_root)),
            rows_html,
        )
        (output_root / ("EMAIL_%d.txt" % bi)).write_text(body + "\n", encoding="utf-8")
        send_email(
            subject="potions: NQ extension band %s %s charts %s (%d/%d)"
            % (entry_mode, sl_mode, tag, bi, len(batches)),
            body=body,
            html=html_body,
            attachments=batch,
        )
        n_sent += 1
        _progress(output_root, "email batch %d/%d attachments=%d (no zip)" % (bi, len(batches), len(batch)))
    return n_sent


def _sample_trades(
    trades: pd.DataFrame,
    *,
    market: str,
    count: int,
    wins: Optional[int] = None,
    losses: Optional[int] = None,
    all_trades: bool = False,
) -> pd.DataFrame:
    sub = trades[trades["market"] == market.upper()].copy()
    if sub.empty:
        return sub
    sub = sub.sort_values(["year", "month", "entry_ts"]).reset_index(drop=True)
    if all_trades:
        return sub
    if wins is None and losses is None:
        half = count // 2
        wins = half
        losses = count - half
    win_df = sub[sub["pnl_usd"] > 0]
    loss_df = sub[sub["pnl_usd"] <= 0]
    parts = []
    if wins:
        parts.append(_even_sample(win_df, min(wins, len(win_df))))
    if losses:
        parts.append(_even_sample(loss_df, min(losses, len(loss_df))))
    out = pd.concat(parts, ignore_index=True) if parts else sub.iloc[0:0]
    if len(out) < count:
        used = set(zip(out["year"], out["month"], out["side"], out["entry_ts"]))
        remain = sub[
            ~sub.apply(lambda r: (r["year"], r["month"], r["side"], r["entry_ts"]) in used, axis=1)
        ]
        need = count - len(out)
        if need > 0 and not remain.empty:
            out = pd.concat([out, _even_sample(remain, need)], ignore_index=True)
    return out.sort_values(["year", "month", "entry_ts"]).reset_index(drop=True)


def _expanding_band(
    paths_by_key: Dict[Tuple[int, int], object],
    market: str,
    year: int,
    month: int,
    *,
    band_mode: str = "expanding",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
):
    if band_mode == "rolling":
        return rolling_band_from_paths(
            list(paths_by_key.values()),
            market,
            year,
            month,
            window=rolling_window,
        )
    prior = [p for p in paths_by_key.values() if (p.year, p.month) < (year, month)]
    if len(prior) < MIN_BAND_MONTHS:
        return None
    return working_band_from_paths(prior, market)


def _draw_band_side(
    ax,
    *,
    month_open: float,
    atr14: float,
    side: str,
    band_min: float,
    band_med: float,
    band_max: float,
    entry_atr: float,
    stop_atr: float,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    fmt: str,
) -> List[float]:
    extras: List[float] = [month_open]
    if side == "long":
        inner = month_open - band_min * atr14
        outer = month_open - band_max * atr14
        med = month_open - band_med * atr14
        entry = month_open - entry_atr * atr14
        stop = month_open - stop_atr * atr14
        label = "dn band"
    else:
        inner = month_open + band_min * atr14
        outer = month_open + band_max * atr14
        med = month_open + band_med * atr14
        entry = month_open + entry_atr * atr14
        stop = month_open + stop_atr * atr14
        label = "up band"
    lo, hi = sorted((inner, outer))
    ax.axhspan(lo, hi, color=BAND_FILL, alpha=0.35, zorder=1)
    for val, name, color, style in [
        (inner, "%s min" % label, BAND_EDGE, ":"),
        (med, "%s med" % label, BAND_MED, "--"),
        (outer, "%s max" % label, BAND_EDGE, ":"),
        (entry, "%s entry" % label, ENTRY_COLOR, "-"),
        (stop, "%s SL" % label, STOP_COLOR, "-"),
        (month_open, "month open / target", TARGET_COLOR, "-"),
    ]:
        ax.hlines(val, t0, t1, colors=color, linestyles=style, linewidth=1.2, alpha=0.9, zorder=5)
        ax.text(
            t0,
            val,
            ("  %s " + fmt) % (name, val),
            color=color,
            fontsize=7.5,
            va="bottom",
            ha="left",
            zorder=6,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 0.8},
        )
        extras.append(val)
    return extras


def _resample_ohlc(bars_1h: pd.DataFrame, candle_tf: str) -> pd.DataFrame:
    """Resample 1h OHLC to ``1h`` (passthrough) or ``4h`` for chart candles."""
    tf = str(candle_tf or "1h").lower().strip()
    if tf in {"1h", "1", "60m"}:
        return bars_1h
    if tf not in {"4h", "4", "240m"}:
        raise ValueError("candle_tf must be 1h or 4h (got %r)" % candle_tf)
    df = bars_1h.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    # Align to NY session clock, then 4h buckets.
    local = df.tz_convert(NY)
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in local.columns:
        agg["volume"] = "sum"
    out = local.resample("4h", label="left", closed="left").agg(agg).dropna(subset=["open", "close"])
    return out


def plot_trade_chart(
    *,
    bars: pd.DataFrame,
    trade: pd.Series,
    band,
    month_open: float,
    atr14: float,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
    entry_mode: str,
    sl_mode: str = "mean_max",
    candle_tf: str = "1h",
) -> None:
    fmt = price_fmt(str(trade["market"]))
    window = bars[(bars.index >= t0) & (bars.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    tf = str(candle_tf or "1h").lower()
    if tf.startswith("4"):
        plot_candles_4h(ax, window)
        tf_label = "4h"
    else:
        plot_candles_1h(ax, window)
        tf_label = "1h"

    up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(band)
    if str(trade["side"]) == "long":
        entry_atr, stop_atr = _entry_stop_atr(
            dn_min, dn_med, dn_max, entry_mode=entry_mode, sl_mode=sl_mode
        )
        extras = _draw_band_side(
            ax,
            month_open=month_open,
            atr14=atr14,
            side="long",
            band_min=dn_min,
            band_med=dn_med,
            band_max=dn_max,
            entry_atr=entry_atr,
            stop_atr=stop_atr,
            t0=t0,
            t1=t1,
            fmt=fmt,
        )
    else:
        entry_atr, stop_atr = _entry_stop_atr(
            up_min, up_med, up_max, entry_mode=entry_mode, sl_mode=sl_mode
        )
        extras = _draw_band_side(
            ax,
            month_open=month_open,
            atr14=atr14,
            side="short",
            band_min=up_min,
            band_med=up_med,
            band_max=up_max,
            entry_atr=entry_atr,
            stop_atr=stop_atr,
            t0=t0,
            t1=t1,
            fmt=fmt,
        )

    entry_ts = pd.Timestamp(trade["entry_ts"])
    exit_ts = pd.Timestamp(trade["exit_ts"])
    entry_px = float(trade["entry_px"])
    exit_px = float(trade["exit_px"])
    marker = "^" if trade["side"] == "long" else "v"
    ax.scatter(
        [entry_ts],
        [entry_px],
        marker=marker,
        s=160,
        color=ENTRY_COLOR,
        edgecolors="white",
        linewidths=0.8,
        zorder=10,
        label="entry",
    )
    ax.scatter(
        [exit_ts],
        [exit_px],
        marker="x",
        s=140,
        color=EXIT_COLOR if float(trade["pnl_usd"]) > 0 else STOP_COLOR,
        linewidths=2.0,
        zorder=11,
        label=str(trade["exit_reason"]),
    )
    extras.extend([entry_px, exit_px, float(trade["stop_px"]), float(trade["target_px"])])

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is None or not np.isfinite(v):
                continue
            y_lo = min(y_lo, float(v))
            y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.05, 1e-4)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(t0, t1)
    ax.set_title(
        "%s %s · %04d-%02d · %s · %s · pnl $%s · %s"
        % (
            trade["market"],
            tf_label,
            int(trade["year"]),
            int(trade["month"]),
            trade["side"],
            trade["exit_reason"],
            "{:,.0f}".format(float(trade["pnl_usd"])),
            entry_mode,
        )
    )
    ax.set_ylabel(str(trade["market"]))
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def build(
    *,
    hub_root: Path,
    output_root: Path,
    market: str,
    count: int,
    trade_file: str,
    email: bool,
    force: bool,
    entry_mode: str = "inner",
    sl_mode: str = "mean_max",
    band_mode: str = "rolling",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    state_root: Optional[Path] = None,
    wins: Optional[int] = None,
    losses: Optional[int] = None,
    all_trades: bool = False,
    candle_tf: str = "1h",
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / market.lower() / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    broker_like = state_root is not None
    if broker_like:
        trades = _broker_trades_df(state_root, market)
        source = str(state_root)
        if trades.empty:
            raise SystemExit("No broker fills for %s" % state_root)
        sample = _sample_trades(
            trades,
            market=market,
            count=count,
            wins=wins,
            losses=losses,
            all_trades=all_trades,
        )
    else:
        trades_path = hub_root / trade_file
        if not trades_path.exists():
            raise SystemExit("Missing trades file: %s" % trades_path)
        trades = pd.read_csv(trades_path)
        source = str(trades_path)
        sample = _sample_trades(
            trades,
            market=market,
            count=count,
            wins=wins,
            losses=losses,
            all_trades=all_trades,
        )
    if sample.empty:
        raise SystemExit("No trades for market %s" % market)

    blurb = _sl_mode_blurb(entry_mode, sl_mode)

    spec = MARKETS[market.upper()]
    bars_1h = load_1h(spec)
    bars = _resample_ohlc(bars_1h, candle_tf)
    paths = collect_path_stats(spec)
    paths_by_key = {(p.year, p.month): p for p in paths}
    tf_label = "4h" if str(candle_tf).lower().startswith("4") else "1h"

    chart_rows: List[dict] = []
    try:
        for i, trade in sample.iterrows():
            year, month = int(trade["year"]), int(trade["month"])
            path = paths_by_key.get((year, month))
            if path is None:
                _progress(output_root, "skip %04d-%02d no path stats" % (year, month))
                continue
            band = _expanding_band(
                paths_by_key,
                market.upper(),
                year,
                month,
                band_mode=band_mode,
                rolling_window=rolling_window,
            )
            if band is None:
                _progress(output_root, "skip %04d-%02d no band" % (year, month))
                continue
            win = [x for x in month_windows(bars_1h, None, None) if x[0] == year and x[1] == month]
            if not win:
                continue
            _, _, m0, m1 = win[0]
            fname = "%04d_%02d_%s_%s.png" % (year, month, trade["side"], slug(str(trade["exit_reason"])))
            rel = "%s/charts/%s" % (market.lower(), fname)
            out_path = output_root / rel
            if out_path.exists() and not force:
                chart_rows.append(
                    {
                        "market": market.upper(),
                        "year": year,
                        "month": month,
                        "side": trade["side"],
                        "exit_reason": trade["exit_reason"],
                        "pnl_usd": float(trade["pnl_usd"]),
                        "chart": rel,
                    }
                )
                continue
            plot_trade_chart(
                bars=bars,
                trade=trade,
                band=band,
                month_open=float(path.month_open),
                atr14=float(path.atr14),
                t0=m0,
                t1=m1,
                out_path=out_path,
                entry_mode=entry_mode,
                sl_mode=sl_mode,
                candle_tf=candle_tf,
            )
            chart_rows.append(
                {
                    "market": market.upper(),
                    "year": year,
                    "month": month,
                    "side": trade["side"],
                    "exit_reason": trade["exit_reason"],
                    "pnl_usd": float(trade["pnl_usd"]),
                    "chart": rel,
                }
            )
            _progress(output_root, "chart %d/%d %s" % (len(chart_rows), len(sample), fname))

        idx_df = pd.DataFrame(chart_rows)
        idx_df.to_csv(output_root / ("%s_INDEX.csv" % market.lower()), index=False)
        index_lines = [
            "# %s band fade trade charts — %s rolling-%dm · %s candles (%d)"
            % (market.upper(), entry_mode, rolling_window, tf_label, len(chart_rows)),
            "",
            "| # | month | side | exit | pnl | chart |",
            "|---:|---|---|---|---:|---|",
        ]
        for j, r in enumerate(chart_rows, 1):
            index_lines.append(
                "| %d | %04d-%02d | %s | %s | %+.0f | [%s](%s) |"
                % (j, r["year"], r["month"], r["side"], r["exit_reason"], r["pnl_usd"], Path(r["chart"]).name, r["chart"])
            )
        (output_root / ("%s_INDEX.md" % market.lower())).write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        n_wins = int((idx_df["pnl_usd"] > 0).sum()) if not idx_df.empty else 0
        n_losses = len(chart_rows) - n_wins
        text = "\n".join(
            [
                "potions: monthly open extension band trade charts — %s %s %s (%s)"
                % (market.upper(), entry_mode, sl_mode, tf_label),
                "",
                "Hub: %s" % output_root,
                "Source: %s" % source,
                "Mode: %s" % ("broker-like Engine+PaperBroker" if broker_like else "pandas walkthrough"),
                "Candles: %s (display only; fills unchanged)" % tf_label,
                "Charts: %d (%d wins / %d losses)" % (len(chart_rows), n_wins, n_losses),
                "",
                blurb,
                "Band: %d-month rolling mean(min/med/max) on monthly ATR."
                % rolling_window,
                "",
            ]
            + [
                "  %04d-%02d %s %s $%s"
                % (r["year"], r["month"], r["side"], r["exit_reason"], "{:,.0f}".format(r["pnl_usd"]))
                for r in chart_rows
            ]
        )
        html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>%s band fade charts — %s rolling-%dm (%d)</h2>
<p>%s</p>
<p>PNG attachments below (no zip).</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>#</th><th>month</th><th>side</th><th>exit</th><th>pnl</th></tr>
%s
</table></body></html>""" % (
            html.escape(market.upper()),
            html.escape(entry_mode),
            rolling_window,
            len(chart_rows),
            html.escape(blurb),
            "\n".join(
                "<tr><td>%d</td><td>%04d-%02d</td><td>%s</td><td>%s</td><td>%+.0f</td></tr>"
                % (j, r["year"], r["month"], r["side"], r["exit_reason"], r["pnl_usd"])
                for j, r in enumerate(chart_rows, 1)
            ),
        )
        (output_root / "EMAIL.txt").write_text(text + "\n", encoding="utf-8")
        (output_root / "EMAIL.html").write_text(html_body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "market": market.upper(),
                    "entry_mode": entry_mode,
                    "sl_mode": sl_mode,
                    "broker_like": broker_like,
                    "rolling_window": rolling_window,
                    "charts": len(chart_rows),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        if email:
            send_email(
                subject="potions: extension band trade charts FAILED",
                body="Hub: %s\n\n%s" % (output_root, err),
            )
        raise

    if email:
        _email_chart_batches(
            output_root=output_root,
            market=market.upper(),
            entry_mode=entry_mode,
            sl_mode=sl_mode,
            rolling_window=rolling_window,
            chart_rows=chart_rows,
            blurb=blurb,
            source=source,
            broker_like=broker_like,
        )

    return chart_rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub-root", type=Path, default=DEFAULT_HUB)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--market", default="NQ")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--trade-file", default="trades.csv")
    ap.add_argument("--entry-mode", default="inner", choices=("inner", "mid", "max", "pct75"))
    ap.add_argument("--sl-mode", default="mean_max")
    ap.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Broker-like Engine state root (fills.csv); charts from actual fills",
    )
    ap.add_argument("--band-mode", default="rolling", choices=("rolling", "expanding"))
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--wins", type=int, default=None, help="Even sample: max wins (with --losses)")
    ap.add_argument("--losses", type=int, default=None, help="Even sample: max losses (with --wins)")
    ap.add_argument("--all-trades", action="store_true", help="Chart every trade (no sampling)")
    ap.add_argument(
        "--candle-tf",
        default="1h",
        choices=("1h", "4h"),
        help="Display candle timeframe (strategy fills unchanged)",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    output_root = args.output_root
    if args.state_root is not None and output_root == DEFAULT_OUT:
        hub = args.state_root.parent.parent if args.state_root.parent.name == "states" else args.state_root.parent
        output_root = hub / ("trade_charts_4h" if args.candle_tf == "4h" else "trade_charts")
    rows = build(
        hub_root=args.hub_root,
        output_root=output_root,
        market=args.market.upper(),
        count=int(args.count),
        trade_file=str(args.trade_file),
        email=bool(args.email),
        force=bool(args.force),
        entry_mode=str(args.entry_mode),
        sl_mode=str(args.sl_mode),
        band_mode=str(args.band_mode),
        rolling_window=int(args.rolling_window),
        state_root=args.state_root,
        wins=args.wins,
        losses=args.losses,
        all_trades=bool(args.all_trades),
        candle_tf=str(args.candle_tf),
    )
    print("Wrote %d charts -> %s" % (len(rows), output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
