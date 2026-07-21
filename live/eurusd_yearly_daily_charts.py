"""EURUSD yearly charts with daily candles + ST ATR×3 + PMC when in-range."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import ensure_eurusd_platform_files
from .ym_hourly_st_pmc_retest_replay import load_prev_month_close_map


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
ATR_LEN = 14
ATR_MULT = 3.0
DEFAULT_OUT = REPO / "live" / "state" / "eurusd_yearly_daily_charts"


def _load_daily(daily_path: Path) -> pd.DataFrame:
    df = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    df = df.set_index("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"])


def _pmc_for_day(ts: pd.Timestamp, pmc_map: Dict[Tuple[int, int], float]) -> Optional[float]:
    return pmc_map.get((int(ts.year), int(ts.month)))


def plot_year(
    daily_st: pd.DataFrame,
    year: int,
    out_path: Path,
    *,
    pmc_map: Dict[Tuple[int, int], float],
) -> dict:
    plot = daily_st.loc[str(year)].copy()
    if plot.empty or len(plot) < 20:
        return {}

    # Need a bit of history for ST continuity into Jan — already computed on full series.
    x = mdates.date2num(plot.index.to_pydatetime())
    width = 0.7

    fig, ax = plt.subplots(figsize=(18, 8))
    up = plot["close"] >= plot["open"]
    colors = np.where(up, "#168a5a", "#c43d3d")
    ax.vlines(x, plot["low"], plot["high"], color=colors, linewidth=0.8, alpha=0.9, zorder=3)
    price_span = float(plot["high"].max() - plot["low"].min())
    min_body = max(price_span * 0.001, 1e-6)
    for xi, o, c, color in zip(x, plot["open"], plot["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width / 2.0, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.35,
                alpha=0.85,
                zorder=4,
            )
        )

    if "supertrend" in plot.columns:
        bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
        bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
        ax.plot(plot.index, bull, color="#009c5b", linewidth=1.8, zorder=6, label="Daily ST bull (ATR×3)")
        ax.plot(plot.index, bear, color="#d62728", linewidth=1.8, zorder=6, label="Daily ST bear (ATR×3)")

    win_lo = float(plot["low"].min())
    win_hi = float(plot["high"].max())

    # Month-start PMC segments: draw only when that month's PMC sits in the year range.
    pmc_drawn_months = 0
    pmc_above = 0
    pmc_below = 0
    drew_pmc_legend = False
    months = sorted({(int(ts.year), int(ts.month)) for ts in plot.index})
    for y, m in months:
        pmc = pmc_map.get((y, m))
        if pmc is None:
            continue
        pmc_f = float(pmc)
        month_mask = (plot.index.year == y) & (plot.index.month == m)
        if not month_mask.any():
            continue
        m_idx = plot.index[month_mask]
        m_lo = float(plot.loc[month_mask, "low"].min())
        m_hi = float(plot.loc[month_mask, "high"].max())
        if m_lo <= pmc_f <= m_hi:
            label = "Prior month close" if not drew_pmc_legend else None
            ax.hlines(
                pmc_f,
                mdates.date2num(m_idx[0].to_pydatetime()),
                mdates.date2num(m_idx[-1].to_pydatetime()),
                colors="#1565c0",
                linestyles="--",
                linewidth=1.3,
                alpha=0.9,
                zorder=5,
                label=label,
            )
            drew_pmc_legend = True
            pmc_drawn_months += 1
        elif pmc_f > m_hi:
            pmc_above += 1
        else:
            pmc_below += 1

    pad = max(price_span * 0.05, 1e-5)
    ax.set_ylim(win_lo - pad, win_hi + pad)

    # Year-level PMC hint using January's PMC vs full-year range (summary badge).
    jan_pmc = pmc_map.get((year, 1)) or _pmc_for_day(plot.index[0], pmc_map)
    pmc_note = ""
    if jan_pmc is not None:
        jp = float(jan_pmc)
        if jp > win_hi:
            pmc_note = " | Jan PMC above %.5f" % jp
            ax.annotate(
                "PMC ▲ often above",
                xy=(0.99, 0.98),
                xycoords="axes fraction",
                ha="right",
                va="top",
                fontsize=9,
                color="#1565c0",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#1565c0", alpha=0.9),
            )
        elif jp < win_lo:
            pmc_note = " | Jan PMC below %.5f" % jp
            ax.annotate(
                "PMC ▼ often below",
                xy=(0.99, 0.02),
                xycoords="axes fraction",
                ha="right",
                va="bottom",
                fontsize=9,
                color="#1565c0",
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#1565c0", alpha=0.9),
            )

    ax.set_title(
        "EURUSD daily — %d | ST ATR(%d)×%g | PMC months on-chart: %d%s"
        % (year, ATR_LEN, ATR_MULT, pmc_drawn_months, pmc_note),
        fontsize=11,
    )
    ax.set_ylabel("EURUSD")
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.6, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlabel("%d (daily candles)" % year)
    fig.autofmt_xdate()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return {
        "year": year,
        "bars": len(plot),
        "pmc_months_on": pmc_drawn_months,
        "pmc_months_above": pmc_above,
        "pmc_months_below": pmc_below,
        "path": out_path.name,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--start-year", type=int, default=0)
    parser.add_argument("--end-year", type=int, default=0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    _, daily_path = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD daily + SuperTrend...", flush=True)
    daily = _load_daily(daily_path)
    daily_st = compute_supertrend(daily, atr_len=ATR_LEN, multiplier=ATR_MULT)
    pmc_map = load_prev_month_close_map(daily_path)

    years = sorted(set(int(y) for y in daily_st.index.year))
    if args.start_year:
        years = [y for y in years if y >= args.start_year]
    if args.end_year:
        years = [y for y in years if y <= args.end_year]

    charts_dir = args.output_root / "charts"
    if charts_dir.exists():
        for p in charts_dir.glob("*.png"):
            p.unlink()
    charts_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for year in years:
        out = charts_dir / ("%d.png" % year)
        meta = plot_year(daily_st, year, out, pmc_map=pmc_map)
        if meta:
            rows.append(meta)
            print("  wrote %d (%d bars)" % (year, meta["bars"]), flush=True)

    lines = [
        "# EURUSD yearly daily charts",
        "",
        "One chart per calendar year. Daily candles, SuperTrend ATR(%d)×%g."
        % (ATR_LEN, ATR_MULT),
        "",
        "- Prior-month close drawn per month only when inside that month’s candle range",
        "- Title notes Jan PMC above/below when off the full-year scale",
        "",
        "| Year | Bars | PMC months on | Above | Below | Chart |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| %d | %d | %d | %d | %d | [charts/%s](charts/%s) |"
            % (
                r["year"],
                r["bars"],
                r["pmc_months_on"],
                r["pmc_months_above"],
                r["pmc_months_below"],
                r["path"],
                r["path"],
            )
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d yearly charts → %s" % (len(rows), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
