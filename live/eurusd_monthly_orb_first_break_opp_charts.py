"""Chart all months with trades for first-break opposite TP25/1R/runner."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INSTRUMENT = "EURUSD"
DEFAULT_STATE = (
    REPO
    / "live"
    / "state"
    / "eurusd_monthly_orb_tp25_close_sl_broker"
    / "states"
    / "eurusd_monthly_orb_first_break_opp_tp25_1r_runner"
)
DEFAULT_OUT = (
    REPO / "live" / "state" / "eurusd_monthly_orb_tp25_close_sl_broker" / "charts" / "first_break_opposite"
)


def _parse_date(ts: str) -> date:
    text = str(ts).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def _month_key(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def _load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = "ts" if "ts" in df.columns else ("ts_event" if "ts_event" in df.columns else None)
    if ts_col is None:
        raise KeyError("bars csv needs ts or ts_event: %s" % path)
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert(None)
    df["ts"] = ts
    df["day"] = ts.dt.normalize()
    return df.sort_values("ts").reset_index(drop=True)


def _load_fills(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert(None)
    df["ts"] = ts
    df["day"] = ts.dt.normalize()
    df["month"] = df["day"].dt.strftime("%Y-%m")
    return df


def _or_levels(month_bars: pd.DataFrame, or_sessions: int = 3) -> Tuple[float, float, float]:
    # OR is always first N *daily* sessions — callers pass daily bars for OR, or
    # precomputed rh/rl.
    orb = month_bars.iloc[:or_sessions]
    rh = float(orb["high"].max())
    rl = float(orb["low"].min())
    return rh, rl, rh - rl


def _plot_month(
    month_bars: pd.DataFrame,
    month_fills: pd.DataFrame,
    out: Path,
    title: str,
    or_sessions: int = 3,
    ylabel: str = "EURUSD",
    *,
    or_rh: Optional[float] = None,
    or_rl: Optional[float] = None,
    legend_loc: str = "upper left",
    x_is_datetime: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    n = len(month_bars)
    if x_is_datetime:
        xs = list(month_bars["ts"])
        width = pd.Timedelta(hours=2.5)
    else:
        xs = list(range(n))
        width = 0.65
    for i, row in enumerate(month_bars.itertuples()):
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        color = "#15803d" if c >= o else "#b91c1c"
        x = xs[i]
        ax.vlines(x, l, h, color=color, linewidth=1.0)
        body_lo, body_hi = min(o, c), max(o, c)
        if body_hi - body_lo < 1e-6:
            body_hi = body_lo + 1e-5
        if x_is_datetime:
            # ~3h body width in day units
            xnum = mdates.date2num(pd.Timestamp(x).to_pydatetime())
            ax.add_patch(
                Rectangle(
                    (xnum - 0.06, body_lo),
                    0.12,
                    body_hi - body_lo,
                    facecolor=color,
                    edgecolor=color,
                    alpha=0.85,
                )
            )
        else:
            ax.add_patch(
                Rectangle((x - width / 2, body_lo), width, body_hi - body_lo, facecolor=color, edgecolor=color, alpha=0.85)
            )

    if or_rh is not None and or_rl is not None:
        rh, rl, r = float(or_rh), float(or_rl), float(or_rh) - float(or_rl)
    else:
        rh, rl, r = _or_levels(month_bars, or_sessions)
    ax.axhline(rh, color="#2563eb", lw=1.4, label="ORH")
    ax.axhline(rl, color="#9333ea", lw=1.4, label="ORL")
    ax.axhline(rh + 0.25 * r, color="#2563eb", ls="--", lw=0.9, alpha=0.8, label="Long 0.25R")
    ax.axhline(rh + 1.0 * r, color="#2563eb", ls=":", lw=0.9, alpha=0.8, label="Long 1R")
    ax.axhline(rh + 2.0 * r, color="#2563eb", ls="-.", lw=0.9, alpha=0.7, label="Long 2R")
    ax.axhline(rl - 0.25 * r, color="#9333ea", ls="--", lw=0.9, alpha=0.8, label="Short 0.25R")
    ax.axhline(rl - 1.0 * r, color="#9333ea", ls=":", lw=0.9, alpha=0.8, label="Short 1R")
    ax.axhline(rl - 2.0 * r, color="#9333ea", ls="-.", lw=0.9, alpha=0.7, label="Short 2R")

    for _, f in month_fills.iterrows():
        fts = pd.Timestamp(f["ts"])
        if x_is_datetime:
            # snap to nearest 4h bar
            diffs = (month_bars["ts"] - fts).abs()
            if diffs.empty:
                continue
            x = month_bars.loc[diffs.idxmin(), "ts"]
        else:
            key = pd.Timestamp(f["day"]).strftime("%Y-%m-%d")
            x_map = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(month_bars["day"])}
            if key not in x_map:
                continue
            x = x_map[key]
        reason = str(f["reason"])
        side = str(f["side"])
        if reason == "entry":
            marker, color, label = ("^" if side == "buy" else "v"), "#0f766e", "entry"
        elif reason == "tp1":
            marker, color, label = ("o", "#ca8a04", "tp1")
        elif reason == "tp2":
            marker, color, label = ("o", "#ea580c", "tp2")
        elif reason == "tp3":
            marker, color, label = ("*", "#dc2626", "tp3")
        else:
            marker, color, label = ("x", "#334155", "close")
        ax.scatter([x], [float(f["price"])], marker=marker, c=color, s=55, zorder=5, label=label)

    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    uniq = []
    for h, lab in zip(handles, labels):
        if lab in seen:
            continue
        seen.add(lab)
        uniq.append((h, lab))
    ax.legend(
        [h for h, _ in uniq],
        [lab for _, lab in uniq],
        loc=legend_loc,
        fontsize=8,
        ncol=2,
        framealpha=0.9,
    )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.18)
    if x_is_datetime:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %Hh"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=45, ha="right")
    else:
        labels_x = [pd.Timestamp(d).strftime("%m-%d") for d in month_bars["day"]]
        step = max(1, len(labels_x) // 10)
        ax.set_xticks(list(range(n))[::step])
        ax.set_xticklabels(labels_x[::step], rotation=45, ha="right")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)
    plt.close(fig)


def run(
    state_root: Path,
    output_root: Path,
    or_sessions: int = 3,
    label: str = "First-break opposite",
    ladder_note: str = "Ladder 1@0.25R / 1@1R / runner@2R.",
    instrument: str = DEFAULT_INSTRUMENT,
    point_value: float = 100000.0,
    fee_per_unit: float = 7.0,
    max_charts: int = 300,
    *,
    chart_bars_path: Optional[Path] = None,
    chart_timeframe: str = "D",
    legend_loc: str = "upper left",
) -> List[Path]:
    instrument = instrument.upper()
    daily = _load_bars(state_root / "bars" / ("%s_D.csv" % instrument))
    if chart_bars_path is not None:
        chart_bars = _load_bars(chart_bars_path)
        x_is_datetime = chart_timeframe.upper() != "D"
    else:
        chart_bars = daily
        x_is_datetime = False
    fills = _load_fills(state_root / "fills.csv")
    trade_months = sorted(fills.loc[fills["reason"] == "entry", "month"].unique())
    if max_charts > 0 and len(trade_months) > max_charts:
        trade_months = trade_months[-max_charts:]
    built: List[Path] = []
    tf_note = "4h candles" if chart_timeframe.upper() == "4H" else "daily candles"
    index_lines = [
        "# %s %s — trade months (%s)" % (instrument, label, tf_note),
        "",
        "Ignore first OR break → arm opposite. %s" % ladder_note,
        "Markers: entry (^/v), tp1, tp2, tp3 (*), close (x). Legend: %s." % legend_loc,
        "",
        "| Month | Entries | Chart |",
        "|---|---:|---|",
    ]
    for mk in trade_months:
        year, month = mk.split("-")
        dbar = daily[daily["day"].dt.strftime("%Y-%m") == mk].copy()
        mbar = chart_bars[chart_bars["day"].dt.strftime("%Y-%m") == mk].copy()
        mfill = fills[fills["month"] == mk].copy()
        if mbar.empty or dbar.empty:
            continue
        rh, rl, _ = _or_levels(dbar, or_sessions)
        n_entry = int((mfill["reason"] == "entry").sum())
        out = output_root / year / ("%s.png" % mk)
        title = "%s %s — %s (%d entries, %s)" % (instrument, label, mk, n_entry, tf_note)
        _plot_month(
            mbar,
            mfill,
            out,
            title,
            or_sessions=or_sessions,
            ylabel=instrument,
            or_rh=rh,
            or_rl=rl,
            legend_loc=legend_loc,
            x_is_datetime=x_is_datetime,
        )
        built.append(out)
        rel = "%s/%s.png" % (year, mk)
        index_lines.append("| %s | %d | [%s](%s) |" % (mk, n_entry, rel, rel))
    index_lines.append("")
    index_lines.append("Total months with trades: %d" % len(built))
    index_lines.append("")
    (output_root / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    # also dump campaign ledger
    FEE = float(fee_per_unit)
    PV = float(point_value)
    rows = []
    for tid, g in fills.groupby("trade_id"):
        g = g.sort_values("day")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        e = e.iloc[0]
        pnl = -FEE * float(e.quantity)
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - e.price) * r.quantity if e.side == "buy" else (e.price - r.price) * r.quantity
            pnl += pts * PV - FEE * float(r.quantity)
        rows.append(
            {
                "trade_id": tid,
                "month": e.month,
                "side": "long" if e.side == "buy" else "short",
                "entry_ts": e.ts,
                "entry": e.price,
                "usd": round(pnl, 2),
                "win": pnl > 0,
                "reasons": ",".join(g.reason.tolist()),
            }
        )
    ledger = pd.DataFrame(rows).sort_values("entry_ts")
    ledger.to_csv(output_root / "campaign_ledger.csv", index=False)
    wr = 100.0 * float(ledger["win"].mean()) if len(ledger) else 0.0
    (output_root / "WINRATE.md").write_text(
        "\n".join(
            [
                "# %s — win rate" % label,
                "",
                "| Metric | Value |",
                "|---|---:|",
                "| Campaigns | %d |" % len(ledger),
                "| Win rate | %.1f%% |" % wr,
                "| Net (ledger) | $%s |" % f"{ledger['usd'].sum():,.0f}",
                "| Avg win | $%s |" % f"{ledger.loc[ledger.win,'usd'].mean():,.0f}",
                "| Avg loss | $%s |" % f"{ledger.loc[~ledger.win,'usd'].mean():,.0f}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Built %d month charts → %s" % (len(built), output_root), flush=True)
    print("WR %.1f%% on %d campaigns" % (wr, len(ledger)), flush=True)
    return built


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--or-sessions", type=int, default=3)
    p.add_argument("--label", type=str, default="First-break opposite")
    p.add_argument(
        "--ladder-note",
        type=str,
        default="Ladder 1@0.25R / 1@1R / runner@2R.",
    )
    p.add_argument("--instrument", type=str, default=DEFAULT_INSTRUMENT)
    p.add_argument("--point-value", type=float, default=100000.0)
    p.add_argument("--fee", type=float, default=7.0)
    p.add_argument("--max-charts", type=int, default=300)
    args = p.parse_args(argv)
    run(
        args.state_root,
        args.output_root,
        or_sessions=args.or_sessions,
        label=args.label,
        ladder_note=args.ladder_note,
        instrument=args.instrument,
        point_value=args.point_value,
        fee_per_unit=args.fee,
        max_charts=args.max_charts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
