"""Weekly 4h level charts for top-3 ATR4 markets (no trades).

Writes under ``live/state/quarterly_atr4_top3_trade_charts/weekly_levels/``.

Scale-down of the quarterly canvas: each PNG is one ISO week of 4h candles
with that week's **opening-day** H/L band and mid ±1..4× ATR(14) (Wilder on 4h,
snapped at the last bar of the opening day). No trade overlays.
"""

from __future__ import annotations

import argparse
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import (
    ATR_COLORS,
    ATR_LEN,
    NY,
    OPEN_WEEK_EDGE,
    OPEN_WEEK_FILL,
    WEEK_SHADE_A,
    WEEK_SHADE_B,
    load_4h,
    plot_candles,
    price_fmt,
    slug,
    week_bounds,
    wilder_atr,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, ensure_4h_csv
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TOP3 = REPO / "live" / "state" / "quarterly_atr4_top3_paths" / "top3_paths.csv"
DEFAULT_HUB = REPO / "live" / "state" / "quarterly_atr4_top3_trade_charts"
DEFAULT_OUT = DEFAULT_HUB / "weekly_levels"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def markets_from_top3(path: Path) -> List[str]:
    df = pd.read_csv(path)
    return sorted({str(m).upper() for m in df["market"].tolist()})


def week_windows(
    bars: pd.DataFrame,
    start: Optional[date],
    end: Optional[date],
) -> List[Tuple[pd.Timestamp, pd.Timestamp, int, int]]:
    """Return (week_start, week_end, iso_year, iso_week) with bars in range."""
    idx = bars.index
    if start is not None:
        idx = idx[idx >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        idx = idx[idx < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if len(idx) == 0:
        return []
    keys = sorted({week_bounds(ts)[0] for ts in idx})
    out: List[Tuple[pd.Timestamp, pd.Timestamp, int, int]] = []
    for w0 in keys:
        w1 = w0 + pd.Timedelta(days=7)
        if bars[(bars.index >= w0) & (bars.index < w1)].empty:
            continue
        iso = w0.isocalendar()
        # pandas <1.1 returns (year, week, weekday) tuple; newer has named attrs.
        if hasattr(iso, "year"):
            iso_year, iso_week = int(iso.year), int(iso.week)
        else:
            iso_year, iso_week = int(iso[0]), int(iso[1])
        out.append((w0, w1, iso_year, iso_week))
    return out


def opening_day_slice(bars: pd.DataFrame, w0: pd.Timestamp, w1: pd.Timestamp) -> pd.DataFrame:
    """First NY calendar day inside the week that has 4h bars (Mon, else next session)."""
    week = bars[(bars.index >= w0) & (bars.index < w1)]
    if week.empty:
        return week
    day0 = week.index[0].normalize()
    day1 = day0 + pd.Timedelta(days=1)
    return week[(week.index >= day0) & (week.index < day1)].copy()


def atr_at_end(atr_series: pd.Series, slice_bars: pd.DataFrame) -> Optional[float]:
    if slice_bars.empty:
        return None
    ts = slice_bars.index[-1]
    if ts in atr_series.index:
        val = float(atr_series.loc[ts])
        if np.isfinite(val) and val > 0:
            return val
    prior = atr_series.loc[:ts].dropna()
    if prior.empty:
        return None
    val = float(prior.iloc[-1])
    return val if np.isfinite(val) and val > 0 else None


def draw_opening_day_range(
    ax,
    od: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if od.empty:
        return None, None, None
    hi = float(od["high"].max())
    lo = float(od["low"].min())
    mid = 0.5 * (hi + lo)
    day_label = od.index[0].strftime("%a %m-%d")
    ax.axhspan(
        lo,
        hi,
        color=OPEN_WEEK_FILL,
        alpha=0.22,
        zorder=1,
        label="Opening day H/L",
    )
    ax.hlines(hi, window_start, window_end, colors=OPEN_WEEK_EDGE, linestyles="-", linewidth=1.15, zorder=5)
    ax.hlines(lo, window_start, window_end, colors=OPEN_WEEK_EDGE, linestyles="-", linewidth=1.15, zorder=5)
    ax.text(
        window_start,
        hi,
        ("  open-day high (%s) " + fmt) % (day_label, hi),
        color=OPEN_WEEK_EDGE,
        fontsize=8,
        va="bottom",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    ax.text(
        window_start,
        lo,
        ("  open-day low (%s) " + fmt) % (day_label, lo),
        color=OPEN_WEEK_EDGE,
        fontsize=8,
        va="top",
        ha="left",
        zorder=6,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.65, "pad": 1.0},
    )
    return hi, lo, mid


def draw_weekly_atr_bands(
    ax,
    mid: float,
    atr: float,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> List[float]:
    levels: List[float] = []
    for k in range(1, 5):
        color = ATR_COLORS[k]
        up = mid + k * atr
        dn = mid - k * atr
        ax.hlines(
            up,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=1.0 if k < 4 else 1.25,
            alpha=0.9,
            zorder=5,
            label="+/- %d×ATR(14) open-day" % k if k == 1 else None,
        )
        ax.hlines(
            dn,
            window_start,
            window_end,
            colors=color,
            linestyles="--",
            linewidth=1.0 if k < 4 else 1.25,
            alpha=0.9,
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
    ax.hlines(
        mid,
        window_start,
        window_end,
        colors="#37474f",
        linestyles=":",
        linewidth=1.0,
        alpha=0.85,
        zorder=5,
        label="Open-day mid",
    )
    levels.append(mid)
    return levels


WEEKLY_OPEN_COLOR = "#6a1b9a"


def draw_weekly_open(
    ax,
    window: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    fmt: str = "%.5f",
) -> Optional[float]:
    """Horizontal level at the first 4h open of the ISO week."""
    if window.empty:
        return None
    weekly_open = float(window["open"].iloc[0])
    ax.hlines(
        weekly_open,
        window_start,
        window_end,
        colors=WEEKLY_OPEN_COLOR,
        linestyles="-",
        linewidth=1.6,
        alpha=0.95,
        zorder=6,
        label="Weekly open",
    )
    ax.text(
        window_start,
        weekly_open,
        ("  weekly open " + fmt) % weekly_open,
        color=WEEKLY_OPEN_COLOR,
        fontsize=8,
        va="bottom",
        ha="left",
        zorder=7,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.0},
    )
    return weekly_open


def shade_days(ax, window_start: pd.Timestamp, window_end: pd.Timestamp) -> None:
    day = window_start.normalize()
    i = 0
    while day < window_end:
        nxt = day + pd.Timedelta(days=1)
        left = max(day, window_start)
        right = min(nxt, window_end)
        if left < right:
            color = WEEK_SHADE_A if (i % 2 == 0) else WEEK_SHADE_B
            ax.axvspan(left, right, color=color, alpha=0.85, zorder=0)
        day = nxt
        i += 1


def plot_week_levels(
    *,
    bars: pd.DataFrame,
    atr_series: pd.Series,
    w0: pd.Timestamp,
    w1: pd.Timestamp,
    iso_year: int,
    iso_week: int,
    out_path: Path,
    symbol: str,
) -> Dict[str, Any]:
    fmt = price_fmt(symbol)
    window = bars[(bars.index >= w0) & (bars.index < w1)].copy()
    od = opening_day_slice(bars, w0, w1)
    atr_val = atr_at_end(atr_series, od)
    open_day = od.index[0].strftime("%Y-%m-%d") if not od.empty else ""

    fig, ax = plt.subplots(figsize=(16, 8.0))
    shade_days(ax, w0, w1)
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
    open_txt = ((" · w.open=" + fmt) % weekly_open) if weekly_open is not None else ""
    ax.set_title(
        "%s 4h · %d-W%02d · open-day %s + ATR bands%s · %s (levels only)"
        % (symbol.upper(), iso_year, iso_week, open_day or "n/a", open_txt, atr_txt)
    )
    ax.set_ylabel(symbol.upper())
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=2)
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
        "open_day": open_day,
        "weekly_open": weekly_open,
        "atr": atr_val,
        "chart": out_path.name,
        "bars": int(len(window)),
    }


def chart_market(
    *,
    market: str,
    output_root: Path,
    start: date,
    end: Optional[date],
    force: bool,
) -> List[dict]:
    market = market.upper()
    if market not in MARKETS:
        raise SystemExit("Unknown market %s" % market)
    spec = MARKETS[market]
    csv_path = ensure_4h_csv(spec)
    path_root = output_root / slug(market)
    charts_root = path_root / "charts"
    if force and path_root.exists():
        import shutil

        shutil.rmtree(path_root)
    charts_root.mkdir(parents=True, exist_ok=True)

    bars = load_4h(csv_path, market)
    atr_series = wilder_atr(bars, ATR_LEN)
    windows = week_windows(bars, start, end)
    _progress(output_root, "%s: %d weeks from %s" % (market, len(windows), start.isoformat()))

    rows: List[dict] = []
    for i, (w0, w1, iso_year, iso_week) in enumerate(windows, start=1):
        name = "%s_4h_%d_W%02d.png" % (slug(market), iso_year, iso_week)
        out_path = charts_root / name
        if out_path.exists() and not force:
            rows.append(
                {
                    "market": market,
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                    "chart": name,
                    "skipped": True,
                }
            )
            continue
        meta = plot_week_levels(
            bars=bars,
            atr_series=atr_series,
            w0=w0,
            w1=w1,
            iso_year=iso_year,
            iso_week=iso_week,
            out_path=out_path,
            symbol=market,
        )
        meta.update(market=market, skipped=False)
        rows.append(meta)
        if i % 25 == 0 or i == len(windows):
            _progress(output_root, "  %s %d/%d weeks" % (market, i, len(windows)))

    pd.DataFrame(rows).to_csv(path_root / "chart_manifest.csv", index=False)
    lines = [
        "# %s — weekly open-day ATR level charts" % market,
        "",
        "Last ~3 years of ISO weeks. 4h candles with **that week's opening-day** H/L, **weekly open**, and ±1..4× ATR(14) @ open-day close.",
        "No trade overlays.",
        "",
        "Weeks: **%d**" % len(rows),
        "",
        "| ISO year | Week | Open day | Chart |",
        "|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            "| %s | %02d | %s | [%s](charts/%s) |"
            % (r["iso_year"], int(r["iso_week"]), r.get("open_day", ""), r["chart"], r["chart"])
        )
    lines.append("")
    (path_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def write_hub_index(output_root: Path, summary_rows: Sequence[dict]) -> None:
    lines = [
        "# Weekly open-day ATR level charts (top-3 markets)",
        "",
        "ISO-week 4h canvases with **opening-day** H/L, **weekly open**, + ATR bands. No trades.",
        "Hub parent: `live/state/quarterly_atr4_top3_trade_charts/`",
        "",
        "| Market | Weeks | Folder |",
        "|---|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            "| %s | %d | [%s](%s/) |"
            % (row["market"], int(row["weeks"]), slug(row["market"]), slug(row["market"]))
        )
    lines.extend(["", "Range: last ~3 years from run start date.", ""])
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    *,
    top3: Path,
    output_root: Path,
    years: float,
    force: bool,
    email: bool,
    markets: Optional[Sequence[str]] = None,
) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    end = date.today()
    start = end - timedelta(days=int(round(365.25 * years)))
    # Snap start to Monday for cleaner week coverage.
    start = start - timedelta(days=start.weekday())
    syms = list(markets) if markets else markets_from_top3(top3)
    rid = begin_run(
        run_class="other",
        variant_slug="quarterly_atr4_weekly_level_charts",
        instrument=",".join(syms),
        hub_path=str(output_root.relative_to(REPO)),
        meta={"years": years, "start": start.isoformat(), "end": end.isoformat(), "levels_only": True, "ref": "open_day"},
    )
    try:
        _progress(
            output_root,
            "START weekly open-day levels markets=%s start=%s end=%s force=%s"
            % (",".join(syms), start.isoformat(), end.isoformat(), force),
        )
        summary: List[dict] = []
        all_rows: List[dict] = []
        for market in syms:
            rows = chart_market(
                market=market,
                output_root=output_root,
                start=start,
                end=end,
                force=force,
            )
            summary.append({"market": market, "weeks": len(rows)})
            all_rows.extend(rows)
        write_hub_index(output_root, summary)
        pd.DataFrame(summary).to_csv(output_root / "summary.csv", index=False)
        (output_root / "RUN_COMPLETE.json").write_text('{"ok": true}\n', encoding="utf-8")

        # Link from parent top3 charts INDEX.
        parent = output_root.parent
        parent_idx = parent / "INDEX.md"
        if parent_idx.exists():
            text = parent_idx.read_text(encoding="utf-8")
            link = (
                "\n## Weekly level charts\n\n"
                "Last ~3 years, **open-day** H/L + ATR bands (no trades): [weekly_levels/](weekly_levels/).\n"
            )
            if "weekly_levels/" not in text:
                parent_idx.write_text(text.rstrip() + "\n" + link, encoding="utf-8")

        email_body = (
            "Top3 ATR4 — weekly open-day level charts\n\n"
            "Hub: %s\n"
            "Markets: %s\n"
            "Range: %s → %s (~%.1fy)\n"
            "Charts: %d weeks total\n"
            "Levels: week opening-day H/L + weekly open + mid ±1..4×ATR(14) @ open-day\n"
            "Trades: none (levels only)\n"
            % (
                output_root,
                ", ".join(syms),
                start.isoformat(),
                end.isoformat(),
                years,
                sum(int(r["weeks"]) for r in summary),
            )
        )
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        if email:
            send_email(
                subject="potions: weekly open-day ATR level charts (~3y)",
                body=email_body,
            )
        complete_run(
            rid,
            trades=sum(int(r["weeks"]) for r in summary),
            meta={"markets": summary},
        )
        _progress(output_root, "DONE weeks=%d" % sum(int(r["weeks"]) for r in summary))
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _progress(output_root, "CRASH %s\n%s" % (exc, traceback.format_exc()))
        if email:
            send_email(
                subject="potions: quarterly ATR4 weekly level charts FAILED",
                body="Hub: %s\n\n%s\n%s" % (output_root, exc, traceback.format_exc()[-2000:]),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top3", type=Path, default=DEFAULT_TOP3)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--years", type=float, default=3.0, help="Lookback years (default 3)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument("--market", action="append", default=[], help="Override top3 markets (repeatable)")
    args = p.parse_args(argv)
    return run(
        top3=args.top3,
        output_root=args.output_root,
        years=float(args.years),
        force=bool(args.force),
        email=bool(args.email),
        markets=args.market or None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
