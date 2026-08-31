"""NQ quarterly-range take / retrace study.

For each calendar quarter, measure the high/low range. When the *next* quarter
takes a prior-quarter extreme (trades beyond prior high or prior low), measure
how far price travels *back into* the prior quarter's range before the next
quarter ends (max fill of the prior range after the break).

Charts: one PNG per calendar year of daily candles. Prior-quarter high/low
horizontals extend through the following quarter only.

Hub: ``live/state/nq_quarterly_range_retrace/``
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .daily_ma50_yearly_charts import plot_candles
from .v2b_st_pmc_alignment_study import REPO


DEFAULT_DAILY = REPO / "nq" / "nq_daily.csv"
DEFAULT_OUT = REPO / "live" / "state" / "nq_quarterly_range_retrace"

Q_COLORS = {
    1: "#1f77b4",
    2: "#ff7f0e",
    3: "#2ca02c",
    4: "#9467bd",
}


@dataclass(frozen=True)
class QuarterRange:
    year: int
    quarter: int
    start: pd.Timestamp
    end: pd.Timestamp
    high: float
    low: float
    high_date: pd.Timestamp
    low_date: pd.Timestamp
    bars: int

    @property
    def label(self) -> str:
        return "%dQ%d" % (self.year, self.quarter)

    @property
    def width(self) -> float:
        return float(self.high - self.low)


@dataclass(frozen=True)
class TakeEvent:
    prior_label: str
    next_label: str
    prior_year: int
    prior_quarter: int
    next_year: int
    next_quarter: int
    side: str  # "take_high" | "take_low"
    prior_high: float
    prior_low: float
    prior_width: float
    break_date: str
    break_price: float
    deepest_retrace_price: float
    deepest_retrace_date: str
    retrace_pts: float
    retrace_pct_of_prior_range: float
    exceeded_opposite_extreme: bool
    next_quarter_ext_beyond_break_pts: float


def _quarter(ts: pd.Timestamp) -> int:
    return int((ts.month - 1) // 3) + 1


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.month.apply(lambda m: int((m - 1) // 3) + 1)
    return df


def build_quarters(daily: pd.DataFrame) -> List[QuarterRange]:
    out: List[QuarterRange] = []
    for (year, q), g in daily.groupby(["year", "quarter"], sort=True):
        if g.empty:
            continue
        hi_i = g["high"].idxmax()
        lo_i = g["low"].idxmin()
        out.append(
            QuarterRange(
                year=int(year),
                quarter=int(q),
                start=pd.Timestamp(g["date"].iloc[0]),
                end=pd.Timestamp(g["date"].iloc[-1]),
                high=float(g["high"].max()),
                low=float(g["low"].min()),
                high_date=pd.Timestamp(g.loc[hi_i, "date"]),
                low_date=pd.Timestamp(g.loc[lo_i, "date"]),
                bars=int(len(g)),
            )
        )
    return out


def _measure_take(
    prior: QuarterRange,
    nxt: QuarterRange,
    next_bars: pd.DataFrame,
    *,
    side: str,
) -> Optional[TakeEvent]:
    """Measure max fill back into prior range after the break during ``nxt``."""

    if prior.width <= 0:
        return None
    bars = next_bars.sort_values("date").reset_index(drop=True)
    if bars.empty:
        return None

    if side == "take_low":
        # Next quarter trades through prior low.
        if float(bars["low"].min()) >= prior.low:
            return None
        hit = bars[bars["low"] <= prior.low]
        if hit.empty:
            return None
        break_row = hit.iloc[0]
        after = bars[bars["date"] >= break_row["date"]]
        # How far back *up* into the prior range (toward prior high).
        deepest_i = after["high"].idxmax()
        deepest_px = float(after.loc[deepest_i, "high"])
        deepest_dt = pd.Timestamp(after.loc[deepest_i, "date"])
        # Points back into range from the broken extreme (prior low).
        inside = min(max(deepest_px, prior.low), prior.high)
        retrace_pts = float(inside - prior.low)
        exceeded = deepest_px > prior.high
        # Continuation beyond the break (further down after the take).
        cont = float(prior.low - float(after["low"].min()))
        break_px = float(break_row["low"])
    elif side == "take_high":
        if float(bars["high"].max()) <= prior.high:
            return None
        hit = bars[bars["high"] >= prior.high]
        if hit.empty:
            return None
        break_row = hit.iloc[0]
        after = bars[bars["date"] >= break_row["date"]]
        # How far back *down* into the prior range (toward prior low).
        deepest_i = after["low"].idxmin()
        deepest_px = float(after.loc[deepest_i, "low"])
        deepest_dt = pd.Timestamp(after.loc[deepest_i, "date"])
        inside = max(min(deepest_px, prior.high), prior.low)
        retrace_pts = float(prior.high - inside)
        exceeded = deepest_px < prior.low
        cont = float(float(after["high"].max()) - prior.high)
        break_px = float(break_row["high"])
    else:
        raise ValueError(side)

    return TakeEvent(
        prior_label=prior.label,
        next_label=nxt.label,
        prior_year=prior.year,
        prior_quarter=prior.quarter,
        next_year=nxt.year,
        next_quarter=nxt.quarter,
        side=side,
        prior_high=prior.high,
        prior_low=prior.low,
        prior_width=prior.width,
        break_date=str(pd.Timestamp(break_row["date"]).date()),
        break_price=break_px,
        deepest_retrace_price=deepest_px,
        deepest_retrace_date=str(deepest_dt.date()),
        retrace_pts=retrace_pts,
        retrace_pct_of_prior_range=100.0 * retrace_pts / prior.width,
        exceeded_opposite_extreme=bool(exceeded),
        next_quarter_ext_beyond_break_pts=max(0.0, cont),
    )


def measure_all_takes(daily: pd.DataFrame, quarters: Sequence[QuarterRange]) -> List[TakeEvent]:
    by_key = {(q.year, q.quarter): q for q in quarters}
    events: List[TakeEvent] = []
    for i, prior in enumerate(quarters[:-1]):
        nxt = quarters[i + 1]
        # Sanity: next should be the chronological successor.
        if (nxt.year, nxt.quarter) != _next_q_key(prior.year, prior.quarter):
            # Still allow if list is contiguous; skip gaps.
            if (nxt.year, nxt.quarter) not in by_key:
                continue
        next_bars = daily[(daily["year"] == nxt.year) & (daily["quarter"] == nxt.quarter)]
        for side in ("take_low", "take_high"):
            ev = _measure_take(prior, nxt, next_bars, side=side)
            if ev is not None:
                events.append(ev)
    return events


def _next_q_key(year: int, quarter: int) -> tuple:
    if quarter == 4:
        return year + 1, 1
    return year, quarter + 1


def _quarter_end_exclusive(year: int, quarter: int) -> pd.Timestamp:
    """First calendar day *after* the quarter (for line extent)."""
    if quarter == 4:
        return pd.Timestamp(year=year + 1, month=1, day=1)
    return pd.Timestamp(year=year, month=quarter * 3 + 1, day=1)


def _next_quarter_span(q: QuarterRange) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Date span of the *next* quarter only (where prior extremes are projected)."""
    ny, nq = _next_q_key(q.year, q.quarter)
    start = _quarter_end_exclusive(q.year, q.quarter)  # first day of next Q
    end = _quarter_end_exclusive(ny, nq) - pd.Timedelta(days=1)
    return start, end


def summarize_events(events: Sequence[TakeEvent]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(e) for e in events])
    return df


def _agg_block(df: pd.DataFrame, title: str) -> List[str]:
    if df.empty:
        return [f"### {title}", "", "_No events._", ""]
    pct = df["retrace_pct_of_prior_range"]
    lines = [
        f"### {title}",
        "",
        f"- N takes: **{len(df)}**",
        f"- Median retrace into prior range: **{pct.median():.1f}%**",
        f"- Mean retrace: **{pct.mean():.1f}%**",
        f"- P25 / P75: **{pct.quantile(0.25):.1f}%** / **{pct.quantile(0.75):.1f}%**",
        f"- Full-range fill (≥100% of prior width toward opposite extreme): "
        f"**{int((pct >= 100.0 - 1e-9).sum())}** ({100.0 * (pct >= 100.0 - 1e-9).mean():.1f}%)",
        f"- Exceeded opposite prior extreme: **{int(df['exceeded_opposite_extreme'].sum())}**",
        "",
    ]
    return lines


def write_summary(
    output_root: Path,
    *,
    daily_path: Path,
    quarters: Sequence[QuarterRange],
    events: Sequence[TakeEvent],
    years: Sequence[int],
) -> Path:
    ev = summarize_events(events)
    lines = [
        "# NQ Quarterly Range Take → Retrace Study",
        "",
        "When quarter **N+1** takes an extreme of quarter **N** (trades beyond "
        "prior high or prior low), measure how far price travels **back into** "
        "N's range during N+1 after the break (max fill toward the opposite extreme, "
        "capped at 100% of prior width for the % metric; `exceeded_opposite_extreme` "
        "flags a full traverse).",
        "",
        f"- Daily source: `{daily_path}`",
        f"- Quarters measured: **{len(quarters)}** ({quarters[0].label} → {quarters[-1].label})",
        f"- Take events: **{len(events)}** "
        f"({sum(1 for e in events if e.side == 'take_low')} take-low / "
        f"{sum(1 for e in events if e.side == 'take_high')} take-high)",
        "",
        "## Aggregate retrace into prior range",
        "",
    ]
    if not ev.empty:
        lines.extend(_agg_block(ev, "All takes"))
        lines.extend(_agg_block(ev[ev["side"] == "take_low"], "Take prior low (then bounce back up into range)"))
        lines.extend(_agg_block(ev[ev["side"] == "take_high"], "Take prior high (then pull back down into range)"))
        # By next quarter seasonality
        lines.extend(["### By next-quarter seasonality", ""])
        lines.append("| Next Q | Side | N | Median % | Mean % | ≥100% |")
        lines.append("|---:|---|---:|---:|---:|---:|")
        for nq in (1, 2, 3, 4):
            for side, label in (("take_low", "take_low"), ("take_high", "take_high")):
                sub = ev[(ev["next_quarter"] == nq) & (ev["side"] == side)]
                if sub.empty:
                    continue
                pct = sub["retrace_pct_of_prior_range"]
                lines.append(
                    "| Q%d | %s | %d | %.1f | %.1f | %d |"
                    % (nq, label, len(sub), pct.median(), pct.mean(), int((pct >= 100).sum()))
                )
        lines.append("")
    lines.extend(
        [
            "## Charts",
            "",
            "One daily-candle chart per calendar year. Prior-quarter high (dashed) and "
            "low (solid) horizontals are drawn across the **next quarter only**. "
            "Markers: triangle = break of prior extreme; diamond = deepest retrace "
            "into prior range.",
            "",
            "| Year | Chart | Takes in year (as next-Q) |",
            "|---:|---|---:|",
        ]
    )
    for y in years:
        n = sum(1 for e in events if e.next_year == y)
        lines.append("| %d | [charts/%d.png](charts/%d.png) | %d |" % (y, y, y, n))
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `quarters.csv` — every quarter high/low",
            "- `takes.csv` — every next-quarter take + retrace metrics",
            "- `charts/` — yearly daily PNGs",
            "",
        ]
    )
    path = output_root / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def plot_year(
    daily: pd.DataFrame,
    quarters: Sequence[QuarterRange],
    events: Sequence[TakeEvent],
    year: int,
    out_path: Path,
) -> None:
    year_bars = daily[daily["year"] == year].copy()
    if year_bars.empty:
        return
    # Pad: last ~20 sessions of prior year + first ~20 of next (for Q4→Q1 lines).
    pad_start = year_bars["date"].iloc[0] - pd.Timedelta(days=40)
    pad_end = year_bars["date"].iloc[-1] + pd.Timedelta(days=40)
    pad = daily[(daily["date"] >= pad_start) & (daily["date"] <= pad_end)].copy()

    fig, ax = plt.subplots(figsize=(18, 9))
    plot_candles(ax, pad)
    ax.axvspan(year_bars["date"].iloc[0], year_bars["date"].iloc[-1], color="#f4f6f8", alpha=0.5, zorder=0)

    # Quarter separators within the year.
    for month in (4, 7, 10):
        ax.axvline(pd.Timestamp(year=year, month=month, day=1), color="#bbbbbb", linewidth=0.8, linestyle=":")

    # Prior-quarter H/L projected across the *next* quarter only.
    drawn_labels = set()
    for q in quarters:
        x0, x1 = _next_quarter_span(q)
        if x1 < pad_start or x0 > pad_end:
            continue
        x0_c = max(x0, pad["date"].iloc[0])
        x1_c = min(x1, pad["date"].iloc[-1])
        if x1_c <= x0_c:
            continue
        color = Q_COLORS[q.quarter]
        for kind, level, ls in (("H", q.high, "--"), ("L", q.low, "-")):
            lab = "%s %s" % (q.label, kind)
            ax.hlines(
                level,
                xmin=mdates.date2num(pd.Timestamp(x0_c).to_pydatetime()),
                xmax=mdates.date2num(pd.Timestamp(x1_c).to_pydatetime()),
                colors=color,
                linestyles=ls,
                linewidth=1.35,
                alpha=0.85,
                label=None if lab in drawn_labels else lab,
            )
            drawn_labels.add(lab)

    # Event markers for takes where next_year == year (or prior spills).
    year_events = [e for e in events if e.next_year == year or e.prior_year == year]
    for e in year_events:
        bdt = pd.Timestamp(e.break_date)
        rdt = pd.Timestamp(e.deepest_retrace_date)
        if pad_start <= bdt <= pad_end:
            marker = "v" if e.side == "take_high" else "^"
            ax.scatter(
                [bdt],
                [e.break_price],
                marker=marker,
                s=55,
                color="#111111",
                zorder=5,
                label=None,
            )
        if pad_start <= rdt <= pad_end:
            ax.scatter(
                [rdt],
                [e.deepest_retrace_price],
                marker="D",
                s=36,
                facecolors="none",
                edgecolors="#111111",
                linewidths=1.0,
                zorder=5,
            )
            ax.annotate(
                "%.0f%%" % e.retrace_pct_of_prior_range,
                (rdt, e.deepest_retrace_price),
                textcoords="offset points",
                xytext=(4, 6),
                fontsize=7,
                color="#333333",
            )

    ax.set_title(
        "NQ daily — %d  |  prior-quarter H/L drawn across next quarter only\n"
        "▲/▼ = take of prior extreme · ◇ = deepest retrace into prior range (%% of prior width)"
        % year
    )
    ax.set_ylabel("NQ")
    ax.grid(True, color="#e1e1e1", linewidth=0.55, alpha=0.7)
    # Compact legend: one entry per quarter label present.
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    if uniq:
        ax.legend(uniq.values(), uniq.keys(), loc="upper left", fontsize=8, ncol=2, framealpha=0.9)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in ax.get_xticklabels():
        label.set_rotation(70)
        label.set_fontsize(7)
    # Focus x on year with light pad.
    ax.set_xlim(pad["date"].iloc[0], pad["date"].iloc[-1])
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def run(daily_path: Path, output_root: Path, *, email: bool = False) -> int:
    if output_root.exists():
        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    daily = load_daily(daily_path)
    quarters = build_quarters(daily)
    events = measure_all_takes(daily, quarters)

    pd.DataFrame([asdict(q) for q in quarters]).to_csv(output_root / "quarters.csv", index=False)
    ev_df = summarize_events(events)
    if not ev_df.empty:
        ev_df.to_csv(output_root / "takes.csv", index=False)
    else:
        (output_root / "takes.csv").write_text(
            "prior_label,next_label,side,retrace_pct_of_prior_range\n", encoding="utf-8"
        )

    years = sorted(int(y) for y in daily["year"].unique())
    for y in years:
        plot_year(daily, quarters, events, y, charts_dir / ("%d.png" % y))

    summary = write_summary(
        output_root, daily_path=daily_path, quarters=quarters, events=events, years=years
    )

    # EMAIL body
    med_all = float(ev_df["retrace_pct_of_prior_range"].median()) if not ev_df.empty else float("nan")
    med_low = (
        float(ev_df.loc[ev_df["side"] == "take_low", "retrace_pct_of_prior_range"].median())
        if not ev_df.empty and (ev_df["side"] == "take_low").any()
        else float("nan")
    )
    med_high = (
        float(ev_df.loc[ev_df["side"] == "take_high", "retrace_pct_of_prior_range"].median())
        if not ev_df.empty and (ev_df["side"] == "take_high").any()
        else float("nan")
    )
    email_lines = [
        "NQ quarterly range take → retrace study complete.",
        "",
        "Hub: %s" % output_root,
        "Quarters: %d (%s → %s)" % (len(quarters), quarters[0].label, quarters[-1].label),
        "Take events: %d" % len(events),
        "Median retrace into prior range (all): %.1f%%" % med_all,
        "  take-low then bounce up: %.1f%%" % med_low,
        "  take-high then pull back: %.1f%%" % med_high,
        "Yearly charts: %d" % len(years),
        "",
        "SUMMARY: %s" % summary,
    ]
    (output_root / "EMAIL.txt").write_text("\n".join(email_lines) + "\n", encoding="utf-8")
    print("Wrote %s" % summary, flush=True)
    print(
        "takes=%d median_retrace=%.1f%% charts=%d" % (len(events), med_all, len(years)),
        flush=True,
    )
    if email:
        from .notify_email import send_email

        send_email(
            subject="potions: NQ quarterly range retrace study complete (median %.0f%%)" % med_all,
            body="\n".join(email_lines) + "\n",
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(args.daily, args.output_root, email=bool(args.email))
    except Exception as exc:
        if args.email:
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: NQ quarterly range retrace FAILED",
                    body="Hub: %s\nError: %s\n" % (args.output_root, exc),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
