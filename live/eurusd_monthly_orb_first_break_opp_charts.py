"""Chart all months with trades for first-break opposite TP25/1R/runner."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

from .eurusd_overnight_sweep import INSTRUMENT


REPO = Path(__file__).resolve().parents[1]
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
    df["day"] = pd.to_datetime(df["ts"]).dt.tz_localize(None).dt.normalize()
    return df.sort_values("day").reset_index(drop=True)


def _load_fills(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["day"] = pd.to_datetime(df["ts"]).dt.tz_localize(None).dt.normalize()
    df["month"] = df["day"].dt.strftime("%Y-%m")
    return df


def _or_levels(month_bars: pd.DataFrame, or_sessions: int = 3) -> Tuple[float, float, float]:
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
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    xs = list(range(len(month_bars)))
    x_map = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(month_bars["day"])}
    width = 0.65
    for i, row in enumerate(month_bars.itertuples()):
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        color = "#15803d" if c >= o else "#b91c1c"
        ax.vlines(i, l, h, color=color, linewidth=1.0)
        body_lo, body_hi = min(o, c), max(o, c)
        if body_hi - body_lo < 1e-6:
            body_hi = body_lo + 1e-5
        ax.add_patch(
            Rectangle((i - width / 2, body_lo), width, body_hi - body_lo, facecolor=color, edgecolor=color, alpha=0.85)
        )

    rh, rl, r = _or_levels(month_bars, or_sessions)
    ax.axhline(rh, color="#2563eb", lw=1.4, label="ORH")
    ax.axhline(rl, color="#9333ea", lw=1.4, label="ORL")
    ax.axhline(rh + 0.25 * r, color="#2563eb", ls="--", lw=0.9, alpha=0.8, label="Long 0.25R")
    ax.axhline(rh + 1.0 * r, color="#2563eb", ls=":", lw=0.9, alpha=0.8, label="Long 1R")
    ax.axhline(rh + 2.0 * r, color="#2563eb", ls="-.", lw=0.9, alpha=0.7, label="Long 2R")
    ax.axhline(rl - 0.25 * r, color="#9333ea", ls="--", lw=0.9, alpha=0.8, label="Short 0.25R")
    ax.axhline(rl - 1.0 * r, color="#9333ea", ls=":", lw=0.9, alpha=0.8, label="Short 1R")
    ax.axhline(rl - 2.0 * r, color="#9333ea", ls="-.", lw=0.9, alpha=0.7, label="Short 2R")
    if len(month_bars) > or_sessions:
        ax.axvline(or_sessions - 0.5, color="#64748b", lw=1.0, alpha=0.7)

    for _, f in month_fills.iterrows():
        key = pd.Timestamp(f["day"]).strftime("%Y-%m-%d")
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

    # de-dupe legend
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    uniq = []
    for h, lab in zip(handles, labels):
        if lab in seen:
            continue
        seen.add(lab)
        uniq.append((h, lab))
    ax.legend([h for h, _ in uniq], [lab for _, lab in uniq], loc="upper left", fontsize=8, ncol=2)
    ax.set_title(title)
    ax.set_ylabel("EURUSD")
    ax.grid(True, alpha=0.18)
    labels_x = [pd.Timestamp(d).strftime("%m-%d") for d in month_bars["day"]]
    step = max(1, len(labels_x) // 10)
    ax.set_xticks(xs[::step])
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
) -> List[Path]:
    bars = _load_bars(state_root / "bars" / ("%s_D.csv" % INSTRUMENT))
    fills = _load_fills(state_root / "fills.csv")
    trade_months = sorted(fills.loc[fills["reason"] == "entry", "month"].unique())
    built: List[Path] = []
    index_lines = [
        "# %s — trade months" % label,
        "",
        "Ignore first OR break → arm opposite. %s" % ladder_note,
        "Markers: entry (^/v), tp1, tp2, tp3 (*), close (x).",
        "",
        "| Month | Entries | Chart |",
        "|---|---:|---|",
    ]
    for mk in trade_months:
        year, month = mk.split("-")
        mbar = bars[bars["day"].dt.strftime("%Y-%m") == mk].copy()
        mfill = fills[fills["month"] == mk].copy()
        if mbar.empty:
            continue
        n_entry = int((mfill["reason"] == "entry").sum())
        out = output_root / year / ("%s.png" % mk)
        title = "EURUSD %s — %s (%d entries)" % (label, mk, n_entry)
        _plot_month(mbar, mfill, out, title, or_sessions=or_sessions)
        built.append(out)
        rel = "%s/%s.png" % (year, mk)
        index_lines.append("| %s | %d | [%s](%s) |" % (mk, n_entry, rel, rel))
    index_lines.append("")
    index_lines.append("Total months with trades: %d" % len(built))
    index_lines.append("")
    (output_root / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    # also dump campaign ledger
    FEE = 7.0
    PV = 100000.0
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
    args = p.parse_args(argv)
    run(
        args.state_root,
        args.output_root,
        or_sessions=args.or_sessions,
        label=args.label,
        ladder_note=args.ladder_note,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
