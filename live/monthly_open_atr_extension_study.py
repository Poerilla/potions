"""Monthly open ±4/6×ATR extension study on 1h bars + sample charts.

Anchor = first 1h bar **open** of the calendar month.
ATR(14) source (``--atr-timeframe``):

- ``1h`` (default): Wilder on 1h bars at opening-week close
  (same convention as ``monthly_atr4_*``).
- ``1M``: Wilder on **monthly** OHLC resampled from 1h; value = prior
  completed month's ATR (causal at month open).

Measures how far price extends from monthly open (in ATR) after the
opening week, and summarizes a hypothetical **fade at ±6×ATR** touch.

Writes hub ``live/state/monthly_open_atr_extension/`` (or
``..._monthly_atr`` when ``--atr-timeframe 1M``) with:
  - ``months.csv`` per-market month stats
  - ``summary.md`` cross-market hit rates / fade diagnostics
  - ``charts/`` top-N extreme months (hourly candles, ±4/±6 bands)
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import ATR_LEN, NY, price_fmt, shade_weeks, slug, wilder_atr
from .monthly_atr4_helpers import load_1h, month_windows, opening_week_slice
from .notify_email import send_email
from .quarterly_atr4_fade_broker import ALL_SYMBOLS, MARKETS, MarketSpec

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_open_atr_extension"
DEFAULT_OUT_MONTHLY_ATR = REPO / "live" / "state" / "monthly_open_atr_extension_monthly_atr"
ATR_TIMEFRAMES = ("1h", "1M")

LEVEL_COLORS = {
    4: "#ef6c00",
    6: "#c62828",
}
MONTH_OPEN_COLOR = "#1565c0"


@dataclass
class MonthRow:
    market: str
    year: int
    month: int
    month_open: float
    atr14: float
    upper4: float
    lower4: float
    upper6: float
    lower6: float
    max_up_atr: float
    max_dn_atr: float
    max_ext_atr: float
    hit_upper4: bool
    hit_lower4: bool
    hit_upper6: bool
    hit_lower6: bool
    fade6_side: str
    fade6_ts: str
    fade6_px: float
    revert_to_4: bool
    revert_to_open: bool
    eom_close: float
    fade6_pnl_atr: float


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _resample_monthly_ohlc(bars: pd.DataFrame) -> pd.DataFrame:
    agg: Dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in bars.columns:
        agg["volume"] = "sum"
    monthly = bars.resample("M", label="right", closed="right").agg(agg)
    return monthly.dropna(subset=["open", "high", "low", "close"])


def _monthly_atr_lookup(bars: pd.DataFrame) -> Dict[Tuple[int, int], float]:
    """Map (year, month) -> prior completed month's Wilder ATR(14)."""
    monthly = _resample_monthly_ohlc(bars)
    atr = wilder_atr(monthly, ATR_LEN)
    keys: List[Tuple[int, int, float]] = []
    for ts, val in atr.items():
        if pd.isna(val) or not (float(val) > 0):
            continue
        keys.append((int(ts.year), int(ts.month), float(val)))
    out: Dict[Tuple[int, int], float] = {}
    for i in range(1, len(keys)):
        y, m, _ = keys[i]
        out[(y, m)] = keys[i - 1][2]
    return out


def _atr_timeframe_label(tf: str) -> str:
    return "monthly ATR(14) @ prior month close" if tf == "1M" else "hourly ATR(14) @ opening-week close"


def _week_end(period_start: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    local = (
        period_start.tz_convert(NY)
        if period_start.tzinfo is not None
        else period_start.tz_localize(NY)
    )
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def plot_candles_1h(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    width_days = (1.0 / 24.0) * 0.58
    x = mdates.date2num(df.index.to_pydatetime())
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    price_span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(price_span * 0.001, 1e-6)
    ax.vlines(x, lows, highs, color=colors, linewidth=0.55, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, opens, closes, colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.25,
                alpha=0.85,
                zorder=4,
            )
        )


def draw_open_atr_levels(
    ax,
    month_open: float,
    atr: float,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    *,
    fmt: str,
) -> List[float]:
    levels: List[float] = []
    ax.hlines(
        month_open,
        window_start,
        window_end,
        colors=MONTH_OPEN_COLOR,
        linestyles="-",
        linewidth=1.35,
        alpha=0.95,
        zorder=5,
        label="Month open",
    )
    ax.text(
        window_start,
        month_open,
        ("  month open " + fmt) % month_open,
        color=MONTH_OPEN_COLOR,
        fontsize=8,
        va="bottom",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    levels.append(month_open)
    for k in (4, 6):
        color = LEVEL_COLORS[k]
        up = month_open + k * atr
        dn = month_open - k * atr
        lw = 1.25 if k == 6 else 1.05
        ax.hlines(
            up,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=lw,
            alpha=0.95,
            zorder=5,
            label="+/- %d×ATR" % k if k == 4 else None,
        )
        ax.hlines(
            dn,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=lw,
            alpha=0.95,
            zorder=5,
        )
        ax.text(
            window_end,
            up,
            (" +%d× " % k) + (fmt % up) + " ",
            color=color,
            fontsize=7.5,
            va="center",
            ha="left",
            zorder=6,
        )
        ax.text(
            window_end,
            dn,
            (" -%d× " % k) + (fmt % dn) + " ",
            color=color,
            fontsize=7.5,
            va="top",
            ha="left",
            zorder=6,
        )
        levels.extend([up, dn])
    return levels


def _scan_month(
    market: MarketSpec,
    bars: pd.DataFrame,
    atr_series: pd.Series,
    year: int,
    month: int,
    m0: pd.Timestamp,
    m1: pd.Timestamp,
    *,
    atr_timeframe: str = "1h",
    monthly_atr_lookup: Optional[Dict[Tuple[int, int], float]] = None,
) -> Optional[MonthRow]:
    month_bars = bars[(bars.index >= m0) & (bars.index < m1)]
    if month_bars.empty:
        return None
    month_open = float(month_bars["open"].iloc[0])
    ow = opening_week_slice(bars, m0)
    if ow.empty:
        return None
    if atr_timeframe == "1M":
        if monthly_atr_lookup is None:
            return None
        atr14 = float(monthly_atr_lookup.get((year, month), float("nan")))
    else:
        atr14 = float(atr_series.loc[ow.index[-1]]) if ow.index[-1] in atr_series.index else float("nan")
        if not (atr14 > 0) or pd.isna(atr14):
            prior = atr_series.loc[: ow.index[-1]].dropna()
            if prior.empty:
                return None
            atr14 = float(prior.iloc[-1])
    if not (atr14 > 0) or pd.isna(atr14):
        return None

    upper4 = month_open + 4.0 * atr14
    lower4 = month_open - 4.0 * atr14
    upper6 = month_open + 6.0 * atr14
    lower6 = month_open - 6.0 * atr14

    _, w1 = _week_end(m0)
    watch = bars[(bars.index >= max(w1, m0)) & (bars.index < m1)]
    if watch.empty:
        return None

    clip_band = 50.0 * atr14
    watch_hi = watch["high"].clip(upper=month_open + clip_band)
    watch_lo = watch["low"].clip(lower=month_open - clip_band)
    max_up = float((watch_hi - month_open).max())
    max_dn = float((month_open - watch_lo).max())
    max_up_atr = max_up / atr14
    max_dn_atr = max_dn / atr14
    max_ext_atr = max(max_up_atr, max_dn_atr)

    hit_upper4 = bool((watch_hi >= upper4).any())
    hit_lower4 = bool((watch_lo <= lower4).any())
    hit_upper6 = bool((watch_hi >= upper6).any())
    hit_lower6 = bool((watch_lo <= lower6).any())

    fade6_side = "none"
    fade6_ts = ""
    fade6_px = float("nan")
    revert_to_4 = False
    revert_to_open = False
    fade6_pnl_atr = float("nan")
    eom_close = float(month_bars["close"].iloc[-1])

    touch_rows: List[Tuple[pd.Timestamp, str, float]] = []
    for ts, hi, lo in zip(watch.index, watch_hi, watch_lo):
        if float(hi) >= upper6:
            touch_rows.append((ts, "upper", upper6))
        if float(lo) <= lower6:
            touch_rows.append((ts, "lower", lower6))
    if touch_rows:
        touch_rows.sort(key=lambda x: x[0])
        fade6_ts_obj, fade6_side, fade6_px = touch_rows[0]
        fade6_ts = fade6_ts_obj.isoformat()
        after = watch[watch.index > fade6_ts_obj]
        if fade6_side == "upper":
            revert_to_4 = bool((after["low"] <= upper4).any())
            revert_to_open = bool((after["low"] <= month_open).any())
            fade6_pnl_atr = (fade6_px - eom_close) / atr14
        else:
            revert_to_4 = bool((after["high"] >= lower4).any())
            revert_to_open = bool((after["high"] >= month_open).any())
            fade6_pnl_atr = (eom_close - fade6_px) / atr14

    return MonthRow(
        market=market.symbol,
        year=year,
        month=month,
        month_open=month_open,
        atr14=atr14,
        upper4=upper4,
        lower4=lower4,
        upper6=upper6,
        lower6=lower6,
        max_up_atr=max_up_atr,
        max_dn_atr=max_dn_atr,
        max_ext_atr=max_ext_atr,
        hit_upper4=hit_upper4,
        hit_lower4=hit_lower4,
        hit_upper6=hit_upper6,
        hit_lower6=hit_lower6,
        fade6_side=fade6_side,
        fade6_ts=fade6_ts,
        fade6_px=fade6_px,
        revert_to_4=revert_to_4,
        revert_to_open=revert_to_open,
        eom_close=eom_close,
        fade6_pnl_atr=fade6_pnl_atr,
    )


def analyze_market(
    market: MarketSpec,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    atr_timeframe: str = "1h",
) -> List[MonthRow]:
    bars = load_1h(market)
    atr = wilder_atr(bars, ATR_LEN)
    monthly_lookup = _monthly_atr_lookup(bars) if atr_timeframe == "1M" else None
    rows: List[MonthRow] = []
    for year, month, m0, m1 in month_windows(bars, start, end):
        row = _scan_month(
            market,
            bars,
            atr,
            year,
            month,
            m0,
            m1,
            atr_timeframe=atr_timeframe,
            monthly_atr_lookup=monthly_lookup,
        )
        if row is not None:
            rows.append(row)
    return rows


def plot_month_chart(
    *,
    bars: pd.DataFrame,
    row: MonthRow,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
) -> None:
    fmt = price_fmt(row.market)
    window = bars[(bars.index >= t0) & (bars.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    plot_candles_1h(ax, window)
    extras = draw_open_atr_levels(
        ax,
        row.month_open,
        row.atr14,
        t0,
        t1,
        fmt=fmt,
    )
    if row.fade6_ts:
        ts = pd.Timestamp(row.fade6_ts)
        if t0 <= ts < t1:
            color = "#6a1b9a"
            marker = "v" if row.fade6_side == "upper" else "^"
            ax.scatter(
                [ts],
                [row.fade6_px],
                marker=marker,
                s=160,
                color=color,
                edgecolors="white",
                linewidths=0.8,
                zorder=10,
                label="6× fade touch",
            )
            extras.append(float(row.fade6_px))

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is None or not np.isfinite(v):
                continue
            y_lo = min(y_lo, float(v))
            y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.04, 1e-4)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(t0, t1)
    fade_txt = ""
    if row.fade6_side != "none":
        fade_txt = " · fade6=%s pnl=%.2f×ATR" % (row.fade6_side, row.fade6_pnl_atr)
    ax.set_title(
        "%s 1h · %04d-%02d · month open ±4/6×ATR · max ext %.2f×ATR%s"
        % (row.market, row.year, row.month, row.max_ext_atr, fade_txt)
    )
    ax.set_ylabel(row.market)
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _summary_table(df: pd.DataFrame, *, atr_timeframe: str) -> List[str]:
    lines = [
        "# Monthly open extension — summary",
        "",
        "Anchor: **first 1h open** of the month. %s." % _atr_timeframe_label(atr_timeframe),
        "Extension measured **after opening week** through month end.",
        "",
        "| Market | Months | P(hit ±4×) | P(hit ±6×) | Med max ext | P95 max ext | Fade6 revert→4 | Fade6 revert→open | Med fade6 pnl (ATR) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for market, g in df.groupby("market", sort=True):
        n = len(g)
        hit4 = float((g["hit_upper4"] | g["hit_lower4"]).mean())
        hit6 = float((g["hit_upper6"] | g["hit_lower6"]).mean())
        med_ext = float(g["max_ext_atr"].median())
        p95_ext = float(g["max_ext_atr"].quantile(0.95))
        fade = g[g["fade6_side"] != "none"]
        rev4 = float(fade["revert_to_4"].mean()) if len(fade) else float("nan")
        revo = float(fade["revert_to_open"].mean()) if len(fade) else float("nan")
        med_pnl = float(fade["fade6_pnl_atr"].median()) if len(fade) else float("nan")
        lines.append(
            "| %s | %d | %.1f%% | %.1f%% | %.2f× | %.2f× | %.1f%% | %.1f%% | %s |"
            % (
                market,
                n,
                100.0 * hit4,
                100.0 * hit6,
                med_ext,
                p95_ext,
                100.0 * rev4 if rev4 == rev4 else 0.0,
                100.0 * revo if revo == revo else 0.0,
                ("%.2f×" % med_pnl) if med_pnl == med_pnl else "n/a",
            )
        )
    return lines


def build(
    *,
    output_root: Path,
    symbols: Sequence[str],
    chart_count: int,
    start: Optional[date],
    end: Optional[date],
    force: bool,
    email: bool,
    atr_timeframe: str = "1h",
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    all_rows: List[MonthRow] = []
    bars_cache: Dict[str, pd.DataFrame] = {}

    try:
        for sym in symbols:
            sym = sym.upper()
            if sym not in MARKETS:
                raise SystemExit("Unknown market %s" % sym)
            spec = MARKETS[sym]
            _progress(output_root, "START %s" % sym)
            rows = analyze_market(spec, start=start, end=end, atr_timeframe=atr_timeframe)
            all_rows.extend(rows)
            bars_cache[sym] = load_1h(spec)
            _progress(output_root, "DONE %s months=%d" % (sym, len(rows)))

        df = pd.DataFrame([asdict(r) for r in all_rows])
        df.to_csv(output_root / "months.csv", index=False)

        summary_lines = _summary_table(df, atr_timeframe=atr_timeframe)
        (output_root / "SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        charts_root = output_root / "charts"
        if force and charts_root.exists():
            import shutil

            shutil.rmtree(charts_root)
        charts_root.mkdir(parents=True, exist_ok=True)

        min_chart_ext = 1.0 if atr_timeframe == "1M" else 8.0
        pick = df.copy()
        pick = pick[(pick["hit_upper6"] | pick["hit_lower6"]) & (pick["max_ext_atr"] >= min_chart_ext)]
        pick["chart_score"] = pick["max_ext_atr"].clip(upper=35.0 if atr_timeframe == "1h" else 6.0)
        pick = pick.sort_values("chart_score", ascending=False)
        if pick.empty:
            pick = df.sort_values("max_ext_atr", ascending=False)
        # One chart per market when possible, then fill by extension.
        chosen: List[pd.Series] = []
        seen_markets: set[str] = set()
        for _, row in pick.iterrows():
            sym = str(row["market"])
            if sym in seen_markets:
                continue
            chosen.append(row)
            seen_markets.add(sym)
            if len(chosen) >= chart_count:
                break
        if len(chosen) < chart_count:
            for _, row in pick.iterrows():
                if any(
                    c["market"] == row["market"]
                    and c["year"] == row["year"]
                    and c["month"] == row["month"]
                    for c in chosen
                ):
                    continue
                chosen.append(row)
                if len(chosen) >= chart_count:
                    break
        pick = pd.DataFrame(chosen)

        chart_rows: List[dict] = []
        for _, r in pick.iterrows():
            sym = str(r["market"]).upper()
            year = int(r["year"])
            month = int(r["month"])
            t0 = pd.Timestamp(year=year, month=month, day=1, tz=NY)
            t1 = t0 + pd.offsets.MonthBegin(1)
            rel = "%s_%04d_%02d.png" % (slug(sym), year, month)
            out_path = charts_root / rel
            row_obj = MonthRow(**{k: r[k] for k in MonthRow.__dataclass_fields__})
            _progress(output_root, "chart %s %04d-%02d max=%.2f×ATR" % (sym, year, month, row_obj.max_ext_atr))
            plot_month_chart(
                bars=bars_cache[sym],
                row=row_obj,
                t0=t0,
                t1=t1,
                out_path=out_path,
            )
            chart_rows.append(
                {
                    "market": sym,
                    "year": year,
                    "month": month,
                    "max_ext_atr": float(r["max_ext_atr"]),
                    "fade6_side": str(r["fade6_side"]),
                    "fade6_pnl_atr": float(r["fade6_pnl_atr"]) if r["fade6_pnl_atr"] == r["fade6_pnl_atr"] else None,
                    "chart": "charts/" + rel,
                }
            )
        pd.DataFrame(chart_rows).to_csv(output_root / "chart_manifest.csv", index=False)

        index_lines = summary_lines + ["", "## Top %d charts (max extension)" % chart_count, ""]
        index_lines.append("| Market | Month | Max ext | Fade6 | PnL@EOM | Chart |")
        index_lines.append("|---|---:|---:|---|---:|---|")
        for cr in chart_rows:
            pnl = cr["fade6_pnl_atr"]
            pnl_s = ("%.2f×" % pnl) if pnl is not None else "n/a"
            index_lines.append(
                "| %s | %04d-%02d | %.2f× | %s | %s | [%s](%s) |"
                % (
                    cr["market"],
                    cr["year"],
                    cr["month"],
                    cr["max_ext_atr"],
                    cr["fade6_side"],
                    pnl_s,
                    Path(cr["chart"]).name,
                    cr["chart"],
                )
            )
        (output_root / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

        atr_tag = "monthly-ATR" if atr_timeframe == "1M" else "hourly-ATR"
        email_body = "\n".join(
            [
                "potions: monthly open ±4/6×ATR extension study complete (%s)" % atr_tag,
                "",
                "Hub: %s" % output_root,
                "ATR: %s" % _atr_timeframe_label(atr_timeframe),
                "Markets: %s" % ", ".join(s.upper() for s in symbols),
                "Months: %d" % len(df),
                "Charts: %d (top extension months)" % len(chart_rows),
                "",
                (output_root / "SUMMARY.md").read_text(encoding="utf-8"),
                "",
                "Charted months:",
            ]
            + [
                "  %s %04d-%02d  max=%.2f×ATR  fade6=%s"
                % (cr["market"], cr["year"], cr["month"], cr["max_ext_atr"], cr["fade6_side"])
                for cr in chart_rows
            ]
        )
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {"ok": True, "months": len(df), "charts": len(chart_rows), "atr_timeframe": atr_timeframe},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: monthly open ATR extension FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: monthly open ATR extension FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        atts = [output_root / cr["chart"] for cr in chart_rows if (output_root / cr["chart"]).exists()]
        send_email(
            subject="potions: monthly open ±4/6×ATR (%s) — %d charts" % (atr_tag, len(chart_rows)),
            body=email_body,
            attachments=atts or None,
        )
        _progress(output_root, "email sent attachments=%d" % len(atts))
    return chart_rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument(
        "--atr-timeframe",
        choices=ATR_TIMEFRAMES,
        default="1h",
        help="ATR bar size: 1h (opening-week close) or 1M (prior month close)",
    )
    ap.add_argument("--symbol", action="append", dest="symbols", help="Repeatable; default all")
    ap.add_argument("--charts", type=int, default=10, help="Top-N months to chart")
    ap.add_argument("--start", type=lambda s: date.fromisoformat(s), default=None)
    ap.add_argument("--end", type=lambda s: date.fromisoformat(s), default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbols or list(ALL_SYMBOLS)
    output_root = args.output_root
    if output_root is None:
        output_root = DEFAULT_OUT_MONTHLY_ATR if args.atr_timeframe == "1M" else DEFAULT_OUT
    rows = build(
        output_root=output_root,
        symbols=symbols,
        chart_count=int(args.charts),
        start=args.start,
        end=args.end,
        force=bool(args.force),
        email=bool(args.email),
        atr_timeframe=str(args.atr_timeframe),
    )
    print("Wrote %d charts -> %s" % (len(rows), output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
